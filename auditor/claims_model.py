"""Ask Muse Spark for structured claims; validation happens in local code."""
from __future__ import annotations

from typing import NamedTuple

from .cancellation import LifecycleError, LifecycleReport, model_evidence
from .model import Explanation, _post
from .workbench_model import _explain


class ClaimsSelection(NamedTuple):
    event_id: str = 'STRUCTURED_CLAIMS'


SYSTEM = '''You are inspecting a fictional, read-only audit. Respond only with a JSON object:
{"claims":[{"scope":"event","event_id":"E-003","field":"status","value":"PENDING_CANCEL"}],
 "interpretation":"A short explanation, clearly identifying missing evidence."}
Create 3 to 8 short, independent factual claims using ONLY supplied evidence.
Each claim has exactly scope, event_id, field, value. Allowed scopes and fields:
event: kind, status, observed_utc, broker_event_utc, cumulative_fill, position_qty, coverage_qty;
quote: age_seconds, age_limit_seconds, session, freshness_status, freshness_reason,
       spread_pct, spread_cap_pct, spread_status, spread_reason;
exposure: gross_pct, gross_cap_pct, gross_status, heat_pct, heat_cap_pct, heat_status;
gate: current_gate, current_reason; finding: code.
For event and finding use the exact event_id. For quote, exposure and gate use null event_id.
Values must be copied as exact JSON scalars, not invented; do not claim unknown values.
A finding is a claim that the named finding code was recorded at that event.
Do not confuse observation time with a separately supplied broker event time.
Interpretation is unverified prose; never assert a real order, overall trade permission, or financial advice.
No markdown fences or extra keys.'''


def generate_claims(report: LifecycleReport, _selection: ClaimsSelection, api_key: str,
                    *, transport=_post) -> Explanation:
    try:
        evidence = model_evidence(report)
    except (LifecycleError, TypeError, AttributeError, ValueError):
        return Explanation('UNAVAILABLE', 'INVALID_EVIDENCE')
    # The event model does not use native JSON-mode parameters. The caller must
    # parse and validate the returned text, and reject malformed or truncated output.
    return _explain(SYSTEM, evidence, api_key, transport)
