"""Synthetic audit memo and unauthenticated, session-local reviewer record.

The memo is constructed from a freshly checked deterministic report. A human
review is a record of a UI action, not a signature, identity check, broker
instruction, verification of model-generated prose, or proof of real facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from .cancellation import LifecycleError, LifecycleReport, markdown_report, model_evidence


class ReviewError(ValueError):
    """A memo or review record does not match the current synthetic case."""


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    trace_id: str
    memo_sha256: str
    decision: str
    evidence_acknowledged: bool
    scope_acknowledged: bool
    recorded_utc: str


def build_memo(report: LifecycleReport) -> dict:
    """Build a structured, model-free memo from revalidated audit results."""
    try:
        evidence = model_evidence(report)
    except (LifecycleError, AttributeError, TypeError, ValueError):
        raise ReviewError('The audit report could not be revalidated.') from None

    q = evidence['quote']
    x = evidence['exposure']
    findings = evidence['findings']
    return {
        'schema': 'mqa.synthetic-review-memo.v1',
        'synthetic': True,
        'trace_id': evidence['trace_id'],
        'scope': 'One fictional case; review is not a broker action or trade authorization.',
        'checks': {
            'G01': {
                'status': q['freshness_status'] if q else 'UNKNOWN',
                'reason': q['freshness_reason'] if q else 'QUOTE_NOT_PROVIDED',
                'age_seconds': q['age_seconds'] if q else None,
                'limit_seconds': q['age_limit_seconds'] if q else None,
                'session': q['session'] if q else None,
            },
            'G02': {
                'status': q['spread_status'] if q else 'UNKNOWN',
                'reason': q['spread_reason'] if q else 'QUOTE_NOT_PROVIDED',
                'spread_pct': q['spread_pct'] if q else None,
                'cap_pct': q['spread_cap_pct'] if q else None,
            },
            'G03': {
                'current_status': evidence['current_gate'],
                'current_reason': evidence['current_reason'],
                'critical_history': [f for f in findings if f['severity'] == 'CRITICAL'],
                'other_findings': [f for f in findings if f['severity'] != 'CRITICAL'],
            },
            'G04': {
                'gross_status': x['gross_status'] if x else 'UNKNOWN',
                'gross_pct': x['gross_pct'] if x else None,
                'gross_cap_pct': x['gross_cap_pct'] if x else None,
                'heat_status': x['heat_status'] if x else 'UNKNOWN',
                'heat_pct': x['heat_pct'] if x else None,
                'heat_cap_pct': x['heat_cap_pct'] if x else None,
            },
        },
        'events': evidence['events'],
        'limitations': [
            'All inputs, event times and protection observations are fictional claims.',
            'Broker and local clock alignment is assumed, not independently verified.',
            'Missing evidence remains unknown and is not a pass.',
            'Model-generated explanations are excluded and are not verified by this memo.',
        ],
    }


def memo_sha256(memo: dict) -> str:
    try:
        content = json.dumps(memo, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ReviewError('Invalid synthetic memo.') from None
    return sha256(content).hexdigest()


def validate_memo(report: LifecycleReport, memo: dict) -> str:
    """Reject altered claims and stale memos; the hash is not authentication."""
    expected = build_memo(report)
    expected_digest = memo_sha256(expected)
    if not isinstance(memo, dict) or memo_sha256(memo) != expected_digest:
        raise ReviewError('The memo does not match this synthetic audit.')
    return expected_digest


def record_review(report: LifecycleReport, memo: dict, decision: str, *,
                  evidence_acknowledged: bool, scope_acknowledged: bool,
                  now: datetime | None = None) -> ReviewRecord:
    digest = validate_memo(report, memo)
    if decision not in {'REVIEWED', 'NEEDS_MANUAL_REVIEW'}:
        raise ReviewError('Unsupported review action.')
    if type(evidence_acknowledged) is not bool or type(scope_acknowledged) is not bool:
        raise ReviewError('Review acknowledgements must be yes or no.')
    if decision == 'REVIEWED' and not (evidence_acknowledged and scope_acknowledged):
        raise ReviewError('Acknowledge the evidence and the simulation scope before marking the memo reviewed.')
    moment = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.utcoffset() is None:
        raise ReviewError('Review time must have a time zone.')
    recorded = moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return ReviewRecord(report.trace_id, digest, decision, evidence_acknowledged,
                        scope_acknowledged, recorded)


def review_download(report: LifecycleReport, memo: dict, record: ReviewRecord) -> str:
    digest = validate_memo(report, memo)
    if (not isinstance(record, ReviewRecord) or record.trace_id != report.trace_id or
            record.memo_sha256 != digest or record.decision not in {'REVIEWED', 'NEEDS_MANUAL_REVIEW'} or
            type(record.evidence_acknowledged) is not bool or type(record.scope_acknowledged) is not bool or
            (record.decision == 'REVIEWED' and not (record.evidence_acknowledged and record.scope_acknowledged))):
        raise ReviewError('The review record does not match this synthetic memo.')
    try:
        datetime.strptime(record.recorded_utc, '%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        raise ReviewError('The review time is invalid.') from None
    lines = [markdown_report(report), '## Reviewer action', '',
             f'- Action: **{record.decision}**',
             f'- Recorded UTC (device clock): `{record.recorded_utc}`',
             f'- Structured memo SHA-256: `{digest}`',
             f'- Evidence acknowledgement: {record.evidence_acknowledged}',
             f'- Simulation scope acknowledgement: {record.scope_acknowledged}', '',
             'This is an unauthenticated, session-local reviewer action. It does not verify identity, '
             'AI-generated text, real broker data, or trade eligibility.', '',
             '## Structured deterministic memo', '', '```json',
             json.dumps(memo, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False),
             '```', '']
    return '\n'.join(lines)
