"""Meta Muse Spark Open model adapter for the Autonomous Risk Cockpit.

Uses Meta's approved hackathon model (meta-models/muse-spark-open-1026 on Baseten).
Transmits generated categorical labels and synthetic numeric metrics.
"""
from __future__ import annotations

import json
from typing import NamedTuple

from .cockpit import CockpitSession, model_cockpit_evidence
from .model import Explanation, _post
from .workbench_model import _explain


class CockpitSelection(NamedTuple):
    event_id: str = "SYNTHETIC_COCKPIT_SUMMARY"


SYSTEM = (
    "You are the Meta AI Autonomous Risk Cockpit Auditor. "
    "Explain the supplied synthetic risk simulation session in concise, authoritative executive English. "
    "1. State how many candidates passed the four illustrative synthetic checks and how many lack required inputs. "
    "2. Specifically highlight autonomous gate blocks (such as spread excess, chop filter, or gross exposure cap breach) "
    "and cite the observed vs limit metrics. Do not assert unverified dollar savings or make trading recommendations. "
    "3. Describe only checks present in the evidence; do not claim overall eligibility or other safeguards. "
    "4. State clearly that all events and metrics shown are synthetic replay data with no live broker connection or order execution. "
    "Use only the provided evidence; do not invent tickers or unrecorded events."
)


def explain_cockpit(session: CockpitSession, _selection: CockpitSelection,
                    api_key: str, *, transport=_post) -> Explanation:
    """Requests a data-minimized Muse Spark explanation for a synthetic cockpit session."""
    if not isinstance(session, CockpitSession):
        return Explanation("UNAVAILABLE", "INVALID_EVIDENCE")
    try:
        evidence = model_cockpit_evidence(session)
    except Exception:
        return Explanation("UNAVAILABLE", "INVALID_EVIDENCE")
    return _explain(SYSTEM, evidence, api_key, transport)
