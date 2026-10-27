"""Synthetic-only missing-evidence workflow for the cancellation gate."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from .cancellation import (LifecycleError, LifecycleReport, MAX_EVENTS, _input_object,
                           audit_trace, model_evidence, parse_trace)


class FollowupError(ValueError):
    """Synthetic evidence could not be appended safely."""


@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    status: str
    reason: str
    request: str
    event_type: str | None


_REQUESTS = {
    'BROKER_TRUTH_UNKNOWN': (
        'A later fictional broker-order observation with status and cumulative fill is needed.', 'BROKER_ORDER'),
    'ORDER_NOT_TERMINAL': (
        'A later fictional terminal order observation and cumulative fill are needed; pending cancel is not terminal.', 'BROKER_ORDER'),
    'POSITION_RECONCILIATION_REQUIRED': (
        'A later fictional position quantity is needed after the positive-fill observation.', 'POSITION_OBSERVED'),
    'PROTECTION_NOT_CONFIRMED': (
        'A later fictional protection status and coverage quantity are needed for the observed position.', 'PROTECTION_OBSERVED'),
    'PROTECTION_QUANTITY_MISMATCH': (
        'A later fictional protection observation is needed to reconcile the recorded quantity mismatch.', 'PROTECTION_OBSERVED'),
}


def evidence_request(report: LifecycleReport) -> EvidenceRequest:
    """Assess only missing lifecycle evidence, not overall trade eligibility."""
    try:
        evidence = model_evidence(report)
    except (LifecycleError, TypeError, AttributeError, ValueError):
        raise FollowupError('Synthetic audit could not be revalidated.') from None
    reason = evidence['current_reason']
    if reason in _REQUESTS:
        request, kind = _REQUESTS[reason]
        return EvidenceRequest('NEEDS_INPUT', reason, request, kind)
    if reason == 'CONTRADICTORY_BROKER_EVIDENCE':
        return EvidenceRequest('REVIEW_REQUIRED', reason,
                               'Conflicting fictional observations require manual review; an appended event cannot erase them.', None)
    if evidence['current_gate'] != 'PASS':
        return EvidenceRequest('REVIEW_REQUIRED', reason, 'The lifecycle gate needs manual review.', None)
    if any(f['severity'] in ('CRITICAL', 'WARNING') for f in evidence['findings']):
        return EvidenceRequest('REVIEW_REQUIRED', reason,
                               'The current gate passes, but recorded warnings or critical findings still require review.', None)
    return EvidenceRequest('READY_FOR_REVIEW', reason,
                           'The current lifecycle check has enough supplied evidence for review; this does not authorize a trade.', None)


def append_followup(report: LifecycleReport, fields: dict) -> str:
    """Append a new fictional observation and return closed-format JSON.

    A generated event ID and the next fictional UTC second avoid arbitrary text.
    Historical observations and findings may not be overwritten or removed.
    """
    request = evidence_request(report)
    expected = {
        'BROKER_ORDER': {'status', 'cumulative_fill'},
        'POSITION_OBSERVED': {'position_qty'},
        'PROTECTION_OBSERVED': {'status', 'coverage_qty'},
    }
    if request.status != 'NEEDS_INPUT' or request.event_type not in expected:
        raise FollowupError('This case is not awaiting an appendable fictional observation.')
    if not isinstance(fields, dict) or set(fields) != expected[request.event_type]:
        raise FollowupError('The fictional follow-up has missing or extra fields.')
    if len(report.events) >= MAX_EVENTS:
        raise FollowupError('The synthetic trace has reached its event limit.')
    ids = {event.event_id for event in report.events}
    new_id = next((f'E-{n:03d}' for n in range(1, 10_000) if f'E-{n:03d}' not in ids), None)
    if new_id is None:
        raise FollowupError('No synthetic event ID is available.')
    try:
        last = datetime.strptime(report.events[-1].observed_utc, '%Y-%m-%dT%H:%M:%SZ')
        observed = (last + timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        original = _input_object(report.source_trace)
        original['events'].append({'event_id': new_id, 'observed_utc': observed,
                                   'type': request.event_type, **fields})
        raw = json.dumps(original, indent=2, allow_nan=False)
        updated = audit_trace(parse_trace(raw))
    except (LifecycleError, TypeError, ValueError, OverflowError):
        raise FollowupError('The fictional follow-up has an invalid value or time.') from None
    if updated.events[:-1] != report.events or not set(report.findings).issubset(updated.findings):
        raise FollowupError('Existing synthetic evidence or findings changed unexpectedly.')
    return raw
