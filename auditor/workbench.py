"""Offline replay of new, tightly scoped synthetic decision cases.

This module is not connected to a broker and never submits an order. Its
policies and inputs are fictional; they do not reproduce the user's bot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
import re
from uuid import NAMESPACE_URL, uuid5


MAX_CASE_BYTES = 65_536
MAX_ATTEMPTS = 12
FORMAT = 'mqa.synthetic-case.v1'
_IDS = {
    'case_id': re.compile(r'^SIM-[0-9]{1,8}$'),
    'attempt_id': re.compile(r'^A-[0-9]{1,6}$'),
    'candidate_id': re.compile(r'^C-[0-9]{1,6}$'),
}
_UTC = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


class CaseError(ValueError):
    """A case cannot be replayed safely; messages never include input values."""


@dataclass(frozen=True, slots=True)
class Quote:
    bid: float
    ask: float
    age_seconds: float
    session: str


@dataclass(frozen=True, slots=True)
class Policy:
    regular_age_seconds: float
    extended_age_seconds: float
    max_spread_percent: float
    max_chase_percent: float


@dataclass(frozen=True, slots=True)
class Attempt:
    attempt_id: str
    candidate_id: str
    timestamp_utc: str
    planned_entry: float


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    quote: Quote
    positions_known: bool
    entries_latched: bool
    policy: Policy
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True, slots=True)
class Gate:
    event_id: str
    gate: str
    outcome: str
    reason_code: str
    observed: float | str | None
    limit: float | str | None
    unit: str


@dataclass(frozen=True, slots=True)
class ReplayAttempt:
    attempt_id: str
    timestamp_utc: str
    simulation_key: str
    decision: str
    gates: tuple[Gate, ...]


@dataclass(frozen=True, slots=True)
class Replay:
    trace_id: str
    case_id: str
    attempts: tuple[ReplayAttempt, ...]


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaseError('Duplicate JSON property.')
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise CaseError('Non-finite JSON number.')


def _object(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise CaseError(f'Unexpected or missing fields in {label}.')
    return value


def _number(value: object, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CaseError(f'{label} must be a finite number.')
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise CaseError(f'{label} must be a finite number.') from None
    if not isfinite(number) or not minimum <= number <= maximum:
        raise CaseError(f'{label} is outside the permitted demonstration range.')
    return number


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not _IDS[name].fullmatch(value):
        raise CaseError(f'{name} must use the documented synthetic identifier format.')
    return value


def parse_case(raw: bytes | str) -> Case:
    """Parse a closed synthetic-case format, rejecting unrecognized fields.

    This is a new event-era format, not a parser for the earlier bot's traces.
    A user-provided synthetic flag is not proof that real data was removed.
    """
    if isinstance(raw, bytes):
        if len(raw) > MAX_CASE_BYTES:
            raise CaseError('Case file is too large.')
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise CaseError('Case file must be UTF-8 JSON.') from None
    elif isinstance(raw, str):
        try:
            encoded = raw.encode('utf-8')
        except UnicodeEncodeError:
            raise CaseError('Case file must be UTF-8 JSON.') from None
        if len(encoded) > MAX_CASE_BYTES:
            raise CaseError('Case file is too large.')
        text = raw
    else:
        raise CaseError('Case must be JSON text.')
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicate_keys,
                           parse_constant=_reject_constant)
    except CaseError:
        raise
    except (ValueError, RecursionError):
        raise CaseError('Case file must be valid JSON.') from None
    root = _object(value, {'format', 'synthetic', 'case_id', 'quote', 'account', 'policy', 'attempts'}, 'case')
    if root['format'] != FORMAT or root['synthetic'] is not True:
        raise CaseError('Only the documented synthetic-case format is supported.')
    case_id = _identifier(root['case_id'], 'case_id')
    q = _object(root['quote'], {'bid', 'ask', 'age_seconds', 'session'}, 'quote')
    bid = _number(q['bid'], 'bid', 0.001, 10_000_000)
    ask = _number(q['ask'], 'ask', 0.001, 10_000_000)
    if ask < bid:
        raise CaseError('Ask cannot be below bid.')
    age = _number(q['age_seconds'], 'quote age', 0, 86_400)
    session = q['session']
    if not isinstance(session, str) or session not in {'REGULAR', 'EXTENDED', 'UNKNOWN'}:
        raise CaseError('Unrecognized synthetic session.')
    quote = Quote(bid, ask, age, session)
    a = _object(root['account'], {'positions_known', 'entries_latched'}, 'account state')
    if type(a['positions_known']) is not bool or type(a['entries_latched']) is not bool:
        raise CaseError('Account-state values must be true or false.')
    p = _object(root['policy'], {'regular_age_seconds', 'extended_age_seconds', 'max_spread_percent', 'max_chase_percent'}, 'policy')
    policy = Policy(
        _number(p['regular_age_seconds'], 'regular freshness limit', 0.001, 86_400),
        _number(p['extended_age_seconds'], 'extended freshness limit', 0.001, 86_400),
        _number(p['max_spread_percent'], 'spread limit', 0.001, 100),
        _number(p['max_chase_percent'], 'chase limit', 0.001, 100),
    )
    if not isinstance(root['attempts'], list) or not 1 <= len(root['attempts']) <= MAX_ATTEMPTS:
        raise CaseError(f'Case must contain 1 to {MAX_ATTEMPTS} attempts.')
    attempts = []
    seen = set()
    previous = None
    for item in root['attempts']:
        obj = _object(item, {'attempt_id', 'candidate_id', 'timestamp_utc', 'planned_entry'}, 'attempt')
        attempt_id = _identifier(obj['attempt_id'], 'attempt_id')
        candidate_id = _identifier(obj['candidate_id'], 'candidate_id')
        timestamp = obj['timestamp_utc']
        if not isinstance(timestamp, str) or not _UTC.fullmatch(timestamp):
            raise CaseError('Attempt timestamp must be UTC with a Z suffix.')
        try:
            current = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            raise CaseError('Attempt timestamp is invalid.') from None
        if attempt_id in seen:
            raise CaseError('Attempt IDs must be unique.')
        if previous is not None and current < previous:
            raise CaseError('Attempts must be in chronological order.')
        seen.add(attempt_id)
        previous = current
        attempts.append(Attempt(attempt_id, candidate_id, timestamp,
                                _number(obj['planned_entry'], 'planned entry', 0.001, 10_000_000)))
    return Case(case_id, quote, a['positions_known'], a['entries_latched'], policy, tuple(attempts))


def replay_case(case: Case) -> Replay:
    """Recompute demo gates; the in-memory duplicate ledger is not durable."""
    if not isinstance(case, Case):
        raise CaseError('A validated case is required.')
    canonical = json.dumps(asdict(case), sort_keys=True, separators=(',', ':'), allow_nan=False)
    trace_id = str(uuid5(NAMESPACE_URL, 'mqa-case-v1:' + canonical))
    quote, policy = case.quote, case.policy
    # Quantize before comparison so the displayed evidence and gate decision
    # agree, including very close boundary values.
    spread = round((quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2) * 100, 6)
    age_limit = {'REGULAR': policy.regular_age_seconds, 'EXTENDED': policy.extended_age_seconds}.get(quote.session)
    reserved = set()
    results = []
    for attempt in case.attempts:
        key = sha256((case.case_id + '|' + attempt.candidate_id).encode()).hexdigest()[:20]
        gate_id = lambda suffix: attempt.attempt_id + '-' + suffix
        if age_limit is None:
            freshness = Gate(gate_id('G01'), 'Quote freshness', 'BLOCK', 'SESSION_POLICY_UNKNOWN', quote.age_seconds, None, 'seconds')
        else:
            stale = quote.age_seconds > age_limit
            freshness = Gate(gate_id('G01'), 'Quote freshness', 'BLOCK' if stale else 'PASS', 'QUOTE_STALE' if stale else 'WITHIN_AGE_LIMIT', quote.age_seconds, age_limit, 'seconds')
        wide = spread > policy.max_spread_percent
        spread_gate = Gate(gate_id('G02'), 'Spread quality', 'VETO' if wide else 'PASS', 'SPREAD_TOO_WIDE' if wide else 'WITHIN_SPREAD_LIMIT', spread, policy.max_spread_percent, 'percent')
        state = 'UNKNOWN' if not case.positions_known else 'LATCHED' if case.entries_latched else 'READY'
        account_gate = Gate(gate_id('G03'), 'Account state', 'PASS' if state == 'READY' else 'BLOCK', {'UNKNOWN': 'POSITIONS_UNKNOWN', 'LATCHED': 'ENTRY_LATCHED', 'READY': 'STATE_READY'}[state], state, 'READY', 'state')
        chase = round(max(0.0, (quote.ask - attempt.planned_entry) / attempt.planned_entry * 100), 6)
        chased = chase > policy.max_chase_percent
        chase_gate = Gate(gate_id('G04'), 'Chase guard', 'VETO' if chased else 'PASS', 'CHASE_TOO_LARGE' if chased else 'WITHIN_CHASE_LIMIT', chase, policy.max_chase_percent, 'percent')
        duplicate = key in reserved
        duplicate_gate = Gate(gate_id('G05'), 'Duplicate simulation', 'BLOCK' if duplicate else 'PASS', 'DUPLICATE_ATTEMPT' if duplicate else 'NEW_SIMULATION_KEY', 'DUPLICATE' if duplicate else 'NEW', 'NEW', 'state')
        gates = (freshness, spread_gate, account_gate, chase_gate, duplicate_gate)
        outcomes = {gate.outcome for gate in gates}
        decision = 'BLOCKED' if 'BLOCK' in outcomes else 'VETOED' if 'VETO' in outcomes else 'ELIGIBLE'
        if decision == 'ELIGIBLE':
            reserved.add(key)
        results.append(ReplayAttempt(attempt.attempt_id, attempt.timestamp_utc, key, decision, gates))
    return Replay(trace_id, case.case_id, tuple(results))


def report_evidence(report: Replay) -> dict:
    """Allowlist structured simulated facts for model or report export."""
    return {
        'schema': 'mqa.synthetic-report.v1',
        'synthetic': True,
        'trace_id': report.trace_id,
        'scope': 'Simulation only. No broker or order execution. Gate outcomes are fixed.',
        'attempts': [
            {'attempt_id': item.attempt_id, 'timestamp_utc': item.timestamp_utc,
             'simulation_key': item.simulation_key, 'decision': item.decision,
             'gates': [asdict(gate) for gate in item.gates]}
            for item in report.attempts
        ],
    }


def markdown_report(report: Replay, explanation: str | None = None) -> str:
    lines = ['# Synthetic Decision Audit', '', f'Trace ID: `{report.trace_id}`',
             f'Case: `{report.case_id}`', '',
             '**Simulation only. No broker connection, real order, or trade authorization.**', '']
    for item in report.attempts:
        lines.extend([f'## Attempt {item.attempt_id}', '', f'- UTC: {item.timestamp_utc}',
                      f'- Simulated decision: **{item.decision}**',
                      f'- Simulation key: `{item.simulation_key}`', '',
                      '| Gate | Outcome | Reason | Observed | Limit |',
                      '| --- | --- | --- | --- | --- |'])
        for gate in item.gates:
            observed = 'unknown' if gate.observed is None else str(gate.observed)
            limit = 'unknown' if gate.limit is None else str(gate.limit)
            lines.append(f'| {gate.event_id}: {gate.gate} | {gate.outcome} | {gate.reason_code} | {observed} {gate.unit} | {limit} {gate.unit} |')
        lines.append('')
    if explanation:
        lines.extend(['## Model explanation — unverified', '',
                      'Compare model statements against the deterministic evidence above.', '',
                      explanation.strip(), ''])
    return '\n'.join(lines)


def sample_cases() -> dict[str, dict]:
    """Fresh fictional fixtures for this workbench, not historical bot traces."""
    def case(name, *, bid=99.95, ask=100.05, age=1.2, known=True, latched=False,
             planned=100.05, session='REGULAR', repeated=False):
        attempts = [{'attempt_id': 'A-001', 'candidate_id': 'C-001',
                     'timestamp_utc': '2026-10-27T14:30:00Z', 'planned_entry': planned}]
        if repeated:
            attempts.append({'attempt_id': 'A-002', 'candidate_id': 'C-001',
                             'timestamp_utc': '2026-10-27T14:30:05Z', 'planned_entry': planned})
        return {'format': FORMAT, 'synthetic': True, 'case_id': 'SIM-' + name,
                'quote': {'bid': bid, 'ask': ask, 'age_seconds': age, 'session': session},
                'account': {'positions_known': known, 'entries_latched': latched},
                'policy': {'regular_age_seconds': 5.0, 'extended_age_seconds': 90.0,
                           'max_spread_percent': 0.4, 'max_chase_percent': 0.35},
                'attempts': attempts}
    return {
        'Wide spread': case('001', bid=99.0, ask=101.0, planned=101.0),
        'Stale quote': case('002', age=16.0),
        'Unknown account state': case('003', known=False),
        'Excessive chase': case('004', planned=99.5),
        'Duplicate attempt': case('005', repeated=True),
        'Unknown session': case('006', session='UNKNOWN'),
    }
