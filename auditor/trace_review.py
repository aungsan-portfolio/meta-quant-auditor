"""Verify recorded synthetic gate events against their stated evidence.

This event-built format is deliberately separate from the participant's older
trace schema. A consistency check cannot prove that an external event occurred.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from uuid import UUID

from .workbench import (CaseError, Gate, MAX_ATTEMPTS, MAX_CASE_BYTES, Replay,
                        ReplayAttempt, _UTC, _identifier, _no_duplicate_keys,
                        _number, _object, _reject_constant, markdown_report)


SCOPE = 'Simulation only. No broker or order execution. Gate outcomes are fixed.'
_KEY = re.compile(r'^[0-9a-f]{20}$')
_GATES = {
    'Quote freshness': ('G01', 'seconds', {'QUOTE_STALE', 'WITHIN_AGE_LIMIT', 'SESSION_POLICY_UNKNOWN'}),
    'Spread quality': ('G02', 'percent', {'SPREAD_TOO_WIDE', 'WITHIN_SPREAD_LIMIT'}),
    'Account state': ('G03', 'state', {'POSITIONS_UNKNOWN', 'ENTRY_LATCHED', 'STATE_READY'}),
    'Chase guard': ('G04', 'percent', {'CHASE_TOO_LARGE', 'WITHIN_CHASE_LIMIT'}),
    'Duplicate simulation': ('G05', 'state', {'DUPLICATE_ATTEMPT', 'NEW_SIMULATION_KEY'}),
}


@dataclass(frozen=True, slots=True)
class Check:
    event_id: str
    status: str
    code: str


@dataclass(frozen=True, slots=True)
class TraceReview:
    trace_id: str
    replay: Replay
    checks: tuple[Check, ...]
    status: str

    @property
    def job_identity(self) -> str:
        # Uploaded records may reuse a trace ID with different contents. Never
        # display an explanation created for another version of the evidence.
        content = json.dumps(review_evidence(self), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return self.trace_id + ':' + sha256(content.encode()).hexdigest()


def _expected(gate: Gate) -> tuple[str, str]:
    """Derive only a demo gate's expected recorded status and reason."""
    if gate.gate == 'Quote freshness':
        if gate.limit is None:
            return 'BLOCK', 'SESSION_POLICY_UNKNOWN'
        return ('BLOCK', 'QUOTE_STALE') if gate.observed > gate.limit else ('PASS', 'WITHIN_AGE_LIMIT')
    if gate.gate == 'Spread quality':
        return ('VETO', 'SPREAD_TOO_WIDE') if gate.observed > gate.limit else ('PASS', 'WITHIN_SPREAD_LIMIT')
    if gate.gate == 'Chase guard':
        return ('VETO', 'CHASE_TOO_LARGE') if gate.observed > gate.limit else ('PASS', 'WITHIN_CHASE_LIMIT')
    if gate.gate == 'Account state':
        return {'UNKNOWN': ('BLOCK', 'POSITIONS_UNKNOWN'), 'LATCHED': ('BLOCK', 'ENTRY_LATCHED'),
                'READY': ('PASS', 'STATE_READY')}[gate.observed]
    return {'DUPLICATE': ('BLOCK', 'DUPLICATE_ATTEMPT'),
            'NEW': ('PASS', 'NEW_SIMULATION_KEY')}[gate.observed]


def review_trace(raw: bytes | str) -> TraceReview:
    """Review strict JSON trace data; unknown fields and unsafe values fail closed."""
    if isinstance(raw, str):
        try:
            raw = raw.encode('utf-8')
        except UnicodeEncodeError:
            raise CaseError('Trace must be UTF-8 JSON.') from None
    if not isinstance(raw, bytes) or len(raw) > MAX_CASE_BYTES:
        raise CaseError('Trace must be bounded UTF-8 JSON.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_no_duplicate_keys,
                           parse_constant=_reject_constant)
    except CaseError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise CaseError('Trace must be valid UTF-8 JSON.') from None
    root = _object(value, {'schema', 'synthetic', 'trace_id', 'scope', 'attempts'}, 'trace')
    if root['schema'] != 'mqa.synthetic-report.v1' or root['synthetic'] is not True or root['scope'] != SCOPE:
        raise CaseError('Only the documented synthetic trace format is supported.')
    trace_id = root['trace_id']
    if not isinstance(trace_id, str):
        raise CaseError('Trace ID must be a UUID.')
    try:
        if str(UUID(trace_id)) != trace_id:
            raise ValueError
    except ValueError:
        raise CaseError('Trace ID must be a canonical UUID.') from None
    if not isinstance(root['attempts'], list) or not 1 <= len(root['attempts']) <= MAX_ATTEMPTS:
        raise CaseError('Trace has an invalid number of attempts.')

    results, checks, seen_attempts = [], [], set()
    previous = None
    ledger, ledger_uncertain = set(), False
    for element in root['attempts']:
        item = _object(element, {'attempt_id', 'timestamp_utc', 'simulation_key', 'decision', 'gates'}, 'attempt')
        attempt_id = _identifier(item['attempt_id'], 'attempt_id')
        if attempt_id in seen_attempts:
            raise CaseError('Attempt IDs must be unique.')
        seen_attempts.add(attempt_id)
        timestamp = item['timestamp_utc']
        if not isinstance(timestamp, str) or not _UTC.fullmatch(timestamp):
            raise CaseError('Attempt timestamp must be UTC with a Z suffix.')
        try:
            current = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            raise CaseError('Attempt timestamp is invalid.') from None
        if previous is not None and current < previous:
            raise CaseError('Attempts must be in chronological order.')
        previous = current
        key, decision = item['simulation_key'], item['decision']
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise CaseError('Invalid synthetic simulation key.')
        if decision not in ('ELIGIBLE', 'BLOCKED', 'VETOED'):
            raise CaseError('Invalid simulation decision.')
        if not isinstance(item['gates'], list) or not 1 <= len(item['gates']) <= len(_GATES):
            raise CaseError('An attempt must contain one to five gate records.')

        gates, names = [], set()
        inconsistent = False
        for element in item['gates']:
            g = _object(element, {'event_id', 'gate', 'outcome', 'reason_code', 'observed', 'limit', 'unit'}, 'gate')
            name = g['gate']
            if not isinstance(name, str) or name not in _GATES or name in names:
                raise CaseError('Unrecognized or repeated gate.')
            names.add(name)
            suffix, unit, reasons = _GATES[name]
            if g['event_id'] != attempt_id + '-' + suffix or g['unit'] != unit:
                raise CaseError('Gate event ID or unit is invalid.')
            if (g['outcome'] not in ('PASS', 'BLOCK', 'VETO') or
                    not isinstance(g['reason_code'], str) or g['reason_code'] not in reasons):
                raise CaseError('Gate outcome or reason code is unsupported.')
            if unit in ('seconds', 'percent'):
                observed = _number(g['observed'], 'gate observation', 0, 1_000_000)
                if g['limit'] is None and name == 'Quote freshness':
                    limit = None
                else:
                    limit = _number(g['limit'], 'gate limit', 0.001, 1_000_000)
            elif name == 'Account state':
                observed, limit = g['observed'], g['limit']
                if observed not in ('UNKNOWN', 'LATCHED', 'READY') or limit != 'READY':
                    raise CaseError('Account state evidence is invalid.')
            else:
                observed, limit = g['observed'], g['limit']
                if observed not in ('NEW', 'DUPLICATE') or limit != 'NEW':
                    raise CaseError('Duplicate evidence is invalid.')
            gate = Gate(g['event_id'], name, g['outcome'], g['reason_code'], observed, limit, unit)
            expected = _expected(gate)
            consistent = (gate.outcome, gate.reason_code) == expected
            checks.append(Check(gate.event_id, 'CONSISTENT' if consistent else 'MISMATCH',
                                'GATE_MATCHES_EVIDENCE' if consistent else 'GATE_DISAGREES_WITH_EVIDENCE'))
            inconsistent |= not consistent
            gates.append(gate)

        complete = names == set(_GATES)
        if not complete:
            checks.append(Check(attempt_id, 'INCOMPLETE', 'MISSING_REQUIRED_GATE'))
            ledger_uncertain = True
        if complete:
            statuses = {gate.outcome for gate in gates}
            expected_decision = 'BLOCKED' if 'BLOCK' in statuses else 'VETOED' if 'VETO' in statuses else 'ELIGIBLE'
            matched = decision == expected_decision
            checks.append(Check(attempt_id, 'CONSISTENT' if matched else 'MISMATCH',
                                'DECISION_MATCHES_GATES' if matched else 'DECISION_DISAGREES_WITH_GATES'))
            inconsistent |= not matched
            duplicate_gate = next(g for g in gates if g.gate == 'Duplicate simulation')
            if ledger_uncertain:
                checks.append(Check(attempt_id, 'UNVERIFIED', 'PRIOR_LEDGER_UNCERTAIN'))
            else:
                duplicate_expected = 'DUPLICATE' if key in ledger else 'NEW'
                matched = duplicate_gate.observed == duplicate_expected
                checks.append(Check(attempt_id, 'CONSISTENT' if matched else 'MISMATCH',
                                    'LEDGER_MATCHES_TRACE' if matched else 'DUPLICATE_LEDGER_MISMATCH'))
                inconsistent |= not matched
            if inconsistent:
                ledger_uncertain = True
            elif decision == 'ELIGIBLE' and not ledger_uncertain:
                ledger.add(key)
        results.append(ReplayAttempt(attempt_id, timestamp, key, decision, tuple(gates)))

    status = 'REVIEW_REQUIRED' if any(c.status == 'MISMATCH' for c in checks) else \
             'INCOMPLETE' if any(c.status in ('INCOMPLETE', 'UNVERIFIED') for c in checks) else 'CONSISTENT'
    replay = Replay(trace_id, 'SIM-IMPORTED', tuple(results))
    return TraceReview(trace_id, replay, tuple(checks), status)


def review_evidence(review: TraceReview) -> dict:
    """Only normalized recorded facts and deterministic check codes are sent."""
    from .workbench import report_evidence
    return {'recorded_trace': report_evidence(review.replay), 'review_status': review.status,
            'checks': [{'event_id': c.event_id, 'status': c.status, 'code': c.code} for c in review.checks]}


def review_markdown(review: TraceReview, explanation: str | None = None) -> str:
    intro = ['# Recorded Synthetic Trace Review', '',
             f'Consistency status: **{review.status}**',
             'A consistency check does not prove that a real-world event occurred.', '',
             '| Event | Check | Code |', '| --- | --- | --- |']
    intro.extend(f'| {c.event_id} | {c.status} | {c.code} |' for c in review.checks)
    return '\n'.join(intro) + '\n\n' + markdown_report(review.replay, explanation)
