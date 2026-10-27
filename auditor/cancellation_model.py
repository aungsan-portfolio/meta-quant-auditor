"""Optional Meta explanation of validated synthetic lifecycle evidence."""
from __future__ import annotations

from typing import NamedTuple

from .cancellation import LifecycleError, LifecycleReport, model_evidence
from .model import Explanation, _post
from .workbench_model import _explain


class LifecycleSelection(NamedTuple):
    event_id: str = 'CANCELLATION_AUDIT'


SYSTEM = (
    'Explain only the supplied synthetic lifecycle audit in clear English. '
    'Refer to event IDs and distinguish a cancel request from a confirmed terminal order. '
    'Distinguish observation time from a supplied broker event time. '
    'A later observation alone does not prove a later execution; reported timestamps are not independently verified. '
    'Explain the supplied quote freshness and spread checks without inventing missing quote values. '
    'Do not omit a recorded critical finding merely because a later current gate passes. '
    'Distinguish gross exposure from supplied stop-risk heat; do not invent missing values. '
    'The deterministic checks are authoritative; do not change their outcomes, '
    'claim real broker execution or give a trade recommendation. '
    'State that this is a synthetic, read-only demonstration.'
)


def explain_lifecycle(report: LifecycleReport, _selection: LifecycleSelection,
                      api_key: str, *, transport=_post) -> Explanation:
    try:
        evidence = model_evidence(report)
    except (LifecycleError, TypeError, AttributeError, ValueError):
        return Explanation('UNAVAILABLE', 'INVALID_EVIDENCE')
    return _explain(SYSTEM, evidence, api_key, transport)
