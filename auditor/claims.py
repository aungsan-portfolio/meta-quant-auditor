"""Compare bounded structured model claims to a synthetic lifecycle report.

Only exact, typed fields are checked. No free-form interpretation, causal claim,
external truth, or trade recommendation is verified by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from math import isfinite
import re

from .cancellation import LifecycleError, LifecycleReport, model_evidence


MAX_RESPONSE_CHARS = 12_000
MAX_CLAIMS = 24
_EVENT_ID = re.compile(r'^E-[0-9]{1,4}$')
_FIELDS = {
    'event': frozenset({'kind', 'status', 'observed_utc', 'broker_event_utc',
                        'cumulative_fill', 'position_qty', 'coverage_qty'}),
    'quote': frozenset({'age_seconds', 'age_limit_seconds', 'session', 'freshness_status',
                        'freshness_reason', 'spread_pct', 'spread_cap_pct', 'spread_status', 'spread_reason'}),
    'exposure': frozenset({'gross_pct', 'gross_cap_pct', 'gross_status',
                           'heat_pct', 'heat_cap_pct', 'heat_status'}),
    'gate': frozenset({'current_gate', 'current_reason'}),
    'finding': frozenset({'code'}),
}


class ClaimsError(ValueError):
    """Invalid or unavailable claims; error messages exclude model output."""


@dataclass(frozen=True, slots=True)
class CheckedClaim:
    index: int
    scope: str
    event_id: str | None
    field: str
    claimed: object
    evidence: object
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimsReport:
    trace_id: str
    claims: tuple[CheckedClaim, ...]
    interpretation: str


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ClaimsError('Duplicate response property.')
        out[key] = value
    return out


def _nonfinite(_: str) -> None:
    raise ClaimsError('Non-finite response number.')


def _scalar(value: object) -> bool:
    if value is None:
        return True
    if type(value) is str:
        return len(value) <= 256
    if type(value) in (int, float):
        try:
            return isfinite(float(value)) and abs(value) <= 1_000_000_000
        except (OverflowError, ValueError):
            return False
    return False


def _matches(expected: object, claimed: object) -> bool | None:
    """None means a type mismatch; bool is never accepted as a number."""
    if type(expected) is str:
        return claimed == expected if type(claimed) is str else None
    if type(expected) in (float, int):
        if type(claimed) not in (int, float):
            return None
        return Decimal(str(expected)) == Decimal(str(claimed))
    return None


def verify_claims(report: LifecycleReport, response_text: str) -> ClaimsReport:
    """Check structured assertions against a freshly revalidated synthetic report.

    Expected JSON: {"claims": [{"scope", "event_id", "field", "value"}],
                    "interpretation": "unverified prose"}.
    A matching scalar says only that the claim matches the supplied synthetic record.
    """
    try:
        evidence = model_evidence(report)
    except (LifecycleError, TypeError, AttributeError, ValueError):
        raise ClaimsError('Synthetic evidence could not be revalidated.') from None
    if not isinstance(response_text, str) or not response_text.strip() or len(response_text) > MAX_RESPONSE_CHARS:
        raise ClaimsError('The structured response is empty or too large.')
    try:
        data = json.loads(response_text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except ClaimsError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ClaimsError('The response is not valid structured JSON.') from None
    if (not isinstance(data, dict) or set(data) != {'claims', 'interpretation'} or
            not isinstance(data['claims'], list) or not 1 <= len(data['claims']) <= MAX_CLAIMS or
            type(data['interpretation']) is not str or len(data['interpretation']) > 4000):
        raise ClaimsError('The response does not match the required claim format.')

    event_map = {e['event_id']: e for e in evidence['events']}
    results = []
    for index, claim in enumerate(data['claims'], 1):
        if not isinstance(claim, dict) or set(claim) != {'scope', 'event_id', 'field', 'value'}:
            raise ClaimsError('A claim is missing fields or contains extra fields.')
        scope, event_id, field, value = (claim[k] for k in ('scope', 'event_id', 'field', 'value'))
        if type(scope) is not str or len(scope) > 32 or type(field) is not str or len(field) > 64:
            raise ClaimsError('A claim label is invalid.')
        if event_id is not None and (type(event_id) is not str or not _EVENT_ID.fullmatch(event_id)):
            raise ClaimsError('A claim event ID is invalid.')
        safe_value = value if _scalar(value) else '[invalid value]'
        status, reason, expected = 'UNVERIFIED', 'UNSUPPORTED_FIELD', None

        if not _scalar(value):
            reason = 'INVALID_VALUE_TYPE'
        elif scope not in _FIELDS or field not in _FIELDS[scope]:
            reason = 'UNSUPPORTED_FIELD'
        elif scope in ('event', 'finding') and event_id is None:
            reason = 'EVENT_ID_REQUIRED'
        elif scope not in ('event', 'finding') and event_id is not None:
            reason = 'UNEXPECTED_EVENT_ID'
        elif scope in ('event', 'finding') and event_id not in event_map:
            reason = 'EVENT_NOT_IN_TRACE'
        else:
            if scope == 'event':
                expected = event_map[event_id][field]
            elif scope == 'finding':
                expected = [f['code'] for f in evidence['findings'] if f['event_id'] == event_id]
            elif scope == 'gate':
                expected = evidence[field]
            else:
                group = evidence[scope]
                expected = group[field] if group is not None else None
            if scope == 'finding':
                if type(value) is not str:
                    reason = 'INVALID_VALUE_TYPE'
                else:
                    status = 'EVIDENCE_MATCH' if value in expected else 'CONTRADICTION'
                    reason = 'RECORDED_FINDING_MATCH' if status == 'EVIDENCE_MATCH' else 'FINDING_NOT_RECORDED_AT_EVENT'
            elif expected is None:
                reason = 'EVIDENCE_UNKNOWN'
            else:
                comparison = _matches(expected, value)
                if comparison is None:
                    reason = 'INVALID_VALUE_TYPE'
                else:
                    status = 'EVIDENCE_MATCH' if comparison else 'CONTRADICTION'
                    reason = 'FIELD_MATCH' if comparison else 'FIELD_MISMATCH'
        results.append(CheckedClaim(index, scope, event_id, field, safe_value, expected, status, reason))
    return ClaimsReport(report.trace_id, tuple(results), data['interpretation'])


def example_claims(report: LifecycleReport) -> str:
    """Fake response for an offline demo; it is never presented as model output."""
    try:
        evidence = model_evidence(report)
    except (LifecycleError, TypeError, AttributeError, ValueError):
        raise ClaimsError('Synthetic evidence could not be revalidated.') from None
    event = next((e for e in evidence['events'] if e['status'] == 'PENDING_CANCEL'), None)
    if event is None:
        event = next((e for e in evidence['events'] if e['status'] is not None), evidence['events'][0])
    used = {e['event_id'] for e in evidence['events']}
    absent = next(f'E-{n:03d}' for n in range(1, 10_000) if f'E-{n:03d}' not in used)
    field = 'status' if event['status'] is not None else 'kind'
    correct = event[field]
    wrong = 'UNKNOWN' if correct != 'UNKNOWN' else 'CANCELED'
    claims = [
        {'scope': 'event', 'event_id': event['event_id'], 'field': field, 'value': correct},
        {'scope': 'event', 'event_id': event['event_id'], 'field': field, 'value': wrong},
        {'scope': 'event', 'event_id': absent, 'field': 'status', 'value': 'CANCELED'},
    ]
    return json.dumps({'claims': claims,
                       'interpretation': 'Fictional demonstration text; no model was called.'})
