"""Single-request Muse Spark adapter for the JSON action protocol (not native tools)."""
from __future__ import annotations

from .agent import AgentResponse
from .model import Transport
from .agent_transport import FixedEndpointResponse, agent_post as _post
from .workbench_model import _explain


_FIXED_AGENT_POST = _post
SYSTEM = '''You audit only a built-in FICTIONAL scenario. Return exactly one JSON object
with exactly three keys: {"action": "...", "args": {}, "reason": "brief action justification"}.
Use bare JSON only, with no prose, markdown, native tool calls, or additional keys.
For the first step, a valid complete response is:
{"action":"run_lifecycle_audit","args":{},"reason":"Check the fictional lifecycle."}
Allowed actions, each at most ONCE per run:
run_lifecycle_audit: args {}. Do this FIRST. Local code computes G01-G04 and critical history.
query_order_status: args {}. Only when missing_evidence.event_type is BROKER_ORDER.
query_position: args {}. Only when missing_evidence.event_type is POSITION_OBSERVED.
query_protection: args {}. Only when missing_evidence.event_type is PROTECTION_OBSERVED.
Queries return scripted FICTIONAL snapshots, not broker truth. Never supply snapshot values.
If a query is unavailable, execution stops NEEDS_INPUT. Do not invent evidence.
compare_claims: args {"claims":[{"scope":"gate","event_id":null,"field":"current_gate","value":"BLOCK"}]}.
request_human_input: args {}. Stops NEEDS_INPUT for operator review.
finish_report: args {"claims":[...],"narrative":"short unverified interpretation"}.
Claims: 1-24 objects each with exactly scope,event_id,field,value. Values are exact JSON scalars.
Scopes/fields: gate=current_gate,current_reason; finding=code (event_id required);
event=kind,status,observed_utc,broker_event_utc,cumulative_fill,position_qty,coverage_qty;
quote=age_seconds,age_limit_seconds,session,freshness_status,freshness_reason,spread_pct,
spread_cap_pct,spread_status,spread_reason;
exposure=gross_pct,gross_cap_pct,gross_status,heat_pct,heat_cap_pct,heat_status.
event/finding use an exact event ID from evidence; other scopes use null event_id.
Choose a needed query until missing evidence is resolved. Then finish_report with claims copied
from CURRENT evidence (not an earlier observation). A later current PASS never erases critical
history. Never change a gate, authorize a trade, or assert real broker facts. Narrative is unverified.
Use remaining_steps and used_actions: no repeated actions, maximum 8 requests, no retries.
reason is a short task justification (1-500 characters), not hidden reasoning.'''


class AgentModelError(RuntimeError):
    pass


def request_action(context: dict, api_key: str, *, transport: Transport | None = None) -> str:
    """Fixed Meta endpoint and a request worker killed at its 30-second deadline."""
    result = _explain(SYSTEM, context, api_key, _post if transport is None else transport)
    if result.status != 'AVAILABLE':
        raise AgentModelError(result.reason)
    return result.text


def request_action_observed(context: dict, api_key: str, *, transport: Transport | None = None) -> AgentResponse:
    """Mark only responses that passed through the configured endpoint worker.

    Injected/custom transports are never labelled live. This is application-level
    telemetry, not a signed provider attestation.
    """
    target = _post if transport is None else transport
    observed_fixed_response = False

    def observe(url, key, payload, timeout):
        nonlocal observed_fixed_response
        result = target(url, key, payload, timeout)
        observed_fixed_response = (transport is None and target is _FIXED_AGENT_POST
                                   and type(result) is FixedEndpointResponse)
        return result

    text = request_action(context, api_key, transport=observe)
    source = 'BASETEN_LIVE_RESPONSE' if observed_fixed_response else 'UNVERIFIED_OR_CUSTOM'
    return AgentResponse(text, source)
