"""Deterministic checks for built-in, fictional quote examples only."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True)
class Scenario:
    slug: str
    title: str
    description: str
    bid: float
    ask: float
    quote_age_seconds: float
    session: str


@dataclass(frozen=True)
class Finding:
    event_id: str
    gate: str
    outcome: str
    reason: str
    observed: float
    limit: float | None
    unit: str


@dataclass(frozen=True)
class AuditTrace:
    trace_id: str
    schema_version: str
    observed_utc: str
    scenario: Scenario
    spread_pct: float
    findings: tuple[Finding, ...]


# Numbers below are fabricated for this prototype; they are not market data.
SCENARIOS = (
    Scenario('wide-spread', 'Wide spread', 'A fresh quote exceeds the sample spread limit.', 99.0, 101.0, 1.2, 'RTH'),
    Scenario('stale-quote', 'Stale quote', 'A tight quote is too old for the sample session.', 99.9, 100.1, 16.0, 'RTH'),
    Scenario('within-limits', 'Within limits', 'Both checks pass in a fictional quote.', 99.95, 100.05, 1.5, 'RTH'),
    Scenario('unknown-session', 'Unknown session', 'Missing session policy blocks the freshness check.', 99.9, 100.1, 1.0, 'UNKNOWN'),
)


def evaluate(scenario: Scenario, *, max_spread_pct: float = 0.4,
             freshness_limits: dict[str, float] | None = None) -> AuditTrace:
    """Compute independent gate results; this does not authorize a trade."""
    policy = {'RTH': 5.0, 'OFF_HOURS': 90.0} if freshness_limits is None else dict(freshness_limits)
    values = (scenario.bid, scenario.ask, scenario.quote_age_seconds, max_spread_pct)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError('Invalid quote inputs')
    if scenario.bid <= 0 or scenario.ask < scenario.bid or scenario.quote_age_seconds < 0 or max_spread_pct <= 0:
        raise ValueError('Invalid quote inputs')
    spread_pct = (scenario.ask - scenario.bid) / ((scenario.ask + scenario.bid) / 2) * 100
    max_age = policy.get(scenario.session)
    if max_age is None:
        freshness = Finding('G01', 'Quote freshness', 'BLOCK', 'SESSION_POLICY_UNKNOWN', scenario.quote_age_seconds, None, 'seconds')
    else:
        if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or not isfinite(max_age) or max_age <= 0:
            raise ValueError('Invalid freshness policy')
        stale = scenario.quote_age_seconds > max_age
        freshness = Finding('G01', 'Quote freshness', 'BLOCK' if stale else 'PASS', 'QUOTE_STALE' if stale else 'WITHIN_AGE_LIMIT', scenario.quote_age_seconds, float(max_age), 'seconds')
    too_wide = spread_pct > max_spread_pct
    spread = Finding('G02', 'Spread quality', 'VETO' if too_wide else 'PASS', 'SPREAD_TOO_WIDE' if too_wide else 'WITHIN_SPREAD_LIMIT', round(spread_pct, 6), float(max_spread_pct), 'percent')
    return AuditTrace(
        trace_id=str(uuid5(NAMESPACE_URL, 'synthetic-audit-demo:' + scenario.slug)),
        schema_version='event-demo/1', observed_utc='2026-10-27T14:30:00Z',
        scenario=scenario, spread_pct=round(spread_pct, 6), findings=(freshness, spread),
    )


def model_evidence(trace: AuditTrace, finding: Finding) -> dict:
    """Only a built-in synthetic event can be serialized to the model."""
    if trace.scenario not in SCENARIOS or trace != evaluate(trace.scenario) or finding not in trace.findings:
        raise ValueError('Only built-in synthetic events are supported')
    return {
        'synthetic': True,
        'trace_id': trace.trace_id,
        'event_id': finding.event_id,
        'observed_utc': trace.observed_utc,
        'gate': finding.gate,
        'outcome': finding.outcome,
        'reason_code': finding.reason,
        'observed': finding.observed,
        'limit': finding.limit,
        'unit': finding.unit,
        'scope': 'One simulated gate; not an overall eligibility or trade decision.',
    }
