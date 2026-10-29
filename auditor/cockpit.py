"""Deterministic Risk Cockpit — Synthetic S&P 500 risk gate replay simulator.

This module is a standalone synthetic simulation built for audit and replay demonstration.
It is not connected to a live broker, does not execute real orders, and does not assert
unverified dollar savings claims. Gate outcomes are computed deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Dict, List, Optional, Tuple


class SignalType(str, Enum):
    BULLISH_BREAKOUT = "BULLISH_BREAKOUT"
    BULLISH_TREND = "BULLISH_TREND"
    MEAN_REVERT = "MEAN_REVERT"
    CHOP_STANDBY = "CHOP_STANDBY"


class GateAction(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    BLOCKED_SPREAD = "BLOCKED_SPREAD"
    BLOCKED_CHOP = "BLOCKED_CHOP"
    BLOCKED_EXPOSURE = "BLOCKED_EXPOSURE"
    BLOCKED_CONFIDENCE = "BLOCKED_CONFIDENCE"
    BLOCKED_INCOMPLETE = "BLOCKED_INCOMPLETE"


ALLOWED_REASON_CODES = frozenset({
    "EXCESS_SPREAD",
    "CHOP_TEXTURE_DETECTED",
    "EXPOSURE_CAP_BREACH",
    "CONFIDENCE_BELOW_THRESHOLD",
    "FOUR_CHECKS_PASS",
    "MISSING_CHOP_SCORE",
    "MISSING_PROJECTED_EXPOSURE",
})


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Configurable risk thresholds for deterministic gate evaluation."""
    max_spread_pct: float = 0.400
    min_ml_confidence: float = 0.600
    max_gross_exposure_pct: float = 28.0
    min_chop_score: float = 60.0


def _valid_number(value: Any, *, low: float = 0.0, high: Optional[float] = None) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and value >= low and (high is None or value <= high))


def _validate_policy(policy: RiskPolicy) -> None:
    if (not isinstance(policy, RiskPolicy)
            or not _valid_number(policy.max_spread_pct)
            or not _valid_number(policy.max_gross_exposure_pct)
            or not _valid_number(policy.min_ml_confidence, high=1.0)
            or not _valid_number(policy.min_chop_score, high=100.0)):
        raise ValueError("Invalid synthetic risk policy")


@dataclass(frozen=True, slots=True)
class TickerState:
    """Synthetic market candidate for deterministic gate inspection."""
    symbol: str
    last_price: float
    bid: float
    ask: float
    spread_pct: float
    volume_shares: int
    atr: float
    ml_signal: SignalType
    ml_confidence: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    profit_target: Optional[float] = None
    status: str = "SYNTHETIC_CANDIDATE"
    shares: int = 0
    chop_score: Optional[float] = None
    projected_exposure_pct: Optional[float] = None

    @property
    def reward_risk_ratio(self) -> float:
        if self.entry_price is None or self.stop_loss is None or self.profit_target is None:
            return 0.0
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.profit_target - self.entry_price)
        if risk <= 0.0:
            return 0.0
        return round(reward / risk, 2)


@dataclass(frozen=True, slots=True)
class AutonomousIntervention:
    """Deterministic risk gate evaluation record with verifiable boundary metrics."""
    event_id: str
    timestamp: str
    symbol: str
    action: GateAction
    reason_code: str
    observed_metric: float
    limit_metric: float
    metric_unit: str
    status: str
    disclaimer: str = "Synthetic gate metric. No broker order or guaranteed dollar savings claimed."

    @property
    def metric_excess_delta(self) -> float:
        """Difference between observed metric and policy limit."""
        return round(self.observed_metric - self.limit_metric, 4)


@dataclass(frozen=True, slots=True)
class CockpitSession:
    """Self-contained synthetic replay scenario for risk gate evaluation."""
    session_id: str
    title: str
    description: str
    gross_exposure_pct: float
    max_exposure_cap_pct: float
    daily_drawdown_pct: float
    max_daily_loss_cap_pct: float
    tickers: tuple[TickerState, ...]
    interventions: tuple[AutonomousIntervention, ...]
    provenance_note: str
    applied_policy: RiskPolicy = RiskPolicy()

    @property
    def trace_id(self) -> str:
        return self.session_id

    @property
    def job_identity(self) -> str:
        """Bind an explanation to the exact evidence previewed for this policy."""
        payload = json.dumps(model_cockpit_evidence(self), sort_keys=True,
                             separators=(',', ':'), allow_nan=False)
        return sha256(payload.encode('utf-8')).hexdigest()


def evaluate_ticker_gate(
    ticker: TickerState,
    policy: RiskPolicy = RiskPolicy(),
    *,
    event_id: str = "GATE-EVAL",
    timestamp: str = "10:00:00 EST",
) -> AutonomousIntervention:
    """Deterministically evaluates risk gates for a ticker state.

    Dynamically calculates gate outcomes based on numerical inputs:
    1. Spread Gate: spread_pct vs policy.max_spread_pct
    2. Chop Filter: chop_score vs policy.min_chop_score (if present)
    3. Exposure Gate: projected_exposure_pct vs policy.max_gross_exposure_pct (if present)
    4. Confidence Gate: ml_confidence vs policy.min_ml_confidence
    """
    _validate_policy(policy)
    if (not _valid_number(ticker.spread_pct)
            or not _valid_number(ticker.ml_confidence, high=1.0)
            or (ticker.chop_score is not None and not _valid_number(ticker.chop_score, high=100.0))
            or (ticker.projected_exposure_pct is not None
                and not _valid_number(ticker.projected_exposure_pct))):
        raise ValueError("Invalid synthetic ticker metric")

    if ticker.spread_pct > policy.max_spread_pct:
        return AutonomousIntervention(
            event_id=event_id,
            timestamp=timestamp,
            symbol=ticker.symbol,
            action=GateAction.BLOCKED_SPREAD,
            reason_code="EXCESS_SPREAD",
            observed_metric=round(ticker.spread_pct, 4),
            limit_metric=round(policy.max_spread_pct, 4),
            metric_unit="percent",
            status="AUTONOMOUS_GATE_VETO",
        )

    if ticker.chop_score is None:
        return AutonomousIntervention(event_id, timestamp, ticker.symbol, GateAction.BLOCKED_INCOMPLETE,
                                      "MISSING_CHOP_SCORE", 0.0, 0.0, "not_available", "INPUT_MISSING")
    if ticker.chop_score is not None:
        if ticker.chop_score < policy.min_chop_score:
            return AutonomousIntervention(
                event_id=event_id,
                timestamp=timestamp,
                symbol=ticker.symbol,
                action=GateAction.BLOCKED_CHOP,
                reason_code="CHOP_TEXTURE_DETECTED",
                observed_metric=round(ticker.chop_score, 2),
                limit_metric=round(policy.min_chop_score, 2),
                metric_unit="score",
                status="FILTER_GATE_VETO",
            )

    if ticker.projected_exposure_pct is None:
        return AutonomousIntervention(event_id, timestamp, ticker.symbol, GateAction.BLOCKED_INCOMPLETE,
                                      "MISSING_PROJECTED_EXPOSURE", 0.0, 0.0, "not_available", "INPUT_MISSING")
    if ticker.projected_exposure_pct is not None:
        if ticker.projected_exposure_pct > policy.max_gross_exposure_pct:
            return AutonomousIntervention(
                event_id=event_id,
                timestamp=timestamp,
                symbol=ticker.symbol,
                action=GateAction.BLOCKED_EXPOSURE,
                reason_code="EXPOSURE_CAP_BREACH",
                observed_metric=round(ticker.projected_exposure_pct, 2),
                limit_metric=round(policy.max_gross_exposure_pct, 2),
                metric_unit="percent",
                status="EXPOSURE_GUARD_VETO",
            )

    if ticker.ml_confidence < policy.min_ml_confidence:
        return AutonomousIntervention(
            event_id=event_id,
            timestamp=timestamp,
            symbol=ticker.symbol,
            action=GateAction.BLOCKED_CONFIDENCE,
            reason_code="CONFIDENCE_BELOW_THRESHOLD",
            observed_metric=round(ticker.ml_confidence, 4),
            limit_metric=round(policy.min_ml_confidence, 4),
            metric_unit="confidence",
            status="CONFIDENCE_GATE_VETO",
        )

    return AutonomousIntervention(
        event_id=event_id,
        timestamp=timestamp,
        symbol=ticker.symbol,
        action=GateAction.AUTHORIZED,
        reason_code="FOUR_CHECKS_PASS",
        observed_metric=round(ticker.spread_pct, 4),
        limit_metric=round(policy.max_spread_pct, 4),
        metric_unit="percent",
        status="SIMULATED_CHECKS_PASS",
    )


def evaluate_cockpit_session(
    session: CockpitSession,
    policy: RiskPolicy = RiskPolicy(),
) -> CockpitSession:
    """Dynamically recalculates all gate interventions across all tickers in a session."""
    _validate_policy(policy)
    recalculated: List[AutonomousIntervention] = []
    for idx, ticker in enumerate(session.tickers, start=1):
        event_id = f"GATE-{idx:03d}"
        interv = evaluate_ticker_gate(ticker, policy, event_id=event_id)
        recalculated.append(interv)

    return CockpitSession(
        session_id=session.session_id,
        title=session.title,
        description=session.description,
        gross_exposure_pct=session.gross_exposure_pct,
        max_exposure_cap_pct=policy.max_gross_exposure_pct,
        daily_drawdown_pct=session.daily_drawdown_pct,
        max_daily_loss_cap_pct=session.max_daily_loss_cap_pct,
        tickers=session.tickers,
        interventions=tuple(recalculated),
        provenance_note=session.provenance_note,
        applied_policy=policy,
    )


def build_default_sessions(policy: RiskPolicy = RiskPolicy()) -> Dict[str, CockpitSession]:
    """Generates synthetic S&P 500 audit replay scenarios with dynamically evaluated gates."""
    s1_tickers = (
        TickerState(
            symbol="NVDA",
            last_price=216.50,
            bid=216.45,
            ask=216.55,
            spread_pct=0.046,
            volume_shares=42_150_000,
            atr=4.20,
            ml_signal=SignalType.BULLISH_BREAKOUT,
            ml_confidence=0.84,
            entry_price=216.50,
            stop_loss=214.20,
            profit_target=222.25,
            status="SIMULATED_POSITION",
            shares=43,
            chop_score=72.0,
            projected_exposure_pct=21.02,
        ),
        TickerState(
            symbol="MSFT",
            last_price=532.10,
            bid=531.95,
            ask=532.25,
            spread_pct=0.056,
            volume_shares=18_400_000,
            atr=6.80,
            ml_signal=SignalType.BULLISH_TREND,
            ml_confidence=0.79,
            entry_price=532.00,
            stop_loss=527.50,
            profit_target=543.25,
            status="SIMULATED_POSITION",
            shares=22,
            chop_score=70.0,
            projected_exposure_pct=21.02,
        ),
        TickerState(
            symbol="TSLA",
            last_price=254.80,
            bid=252.50,
            ask=257.10,
            spread_pct=1.805,
            volume_shares=65_300_000,
            atr=8.10,
            ml_signal=SignalType.BULLISH_BREAKOUT,
            ml_confidence=0.76,
            status="SYNTHETIC_CANDIDATE",
            chop_score=70.0,
            projected_exposure_pct=25.0,
        ),
        TickerState(
            symbol="AAPL",
            last_price=232.40,
            bid=232.35,
            ask=232.45,
            spread_pct=0.043,
            volume_shares=31_200_000,
            atr=2.90,
            ml_signal=SignalType.CHOP_STANDBY,
            ml_confidence=0.52,
            chop_score=52.0,
            status="SYNTHETIC_CANDIDATE",
            projected_exposure_pct=23.0,
        ),
    )

    s1_raw = CockpitSession(
        session_id="sp500-morning-session",
        title="S&P 500 Morning Session — Synthetic Gate Replay",
        description="Fictional market replay simulating deterministic spread spike and chop filter gate interventions.",
        gross_exposure_pct=21.02,
        max_exposure_cap_pct=28.0,
        daily_drawdown_pct=0.0,
        max_daily_loss_cap_pct=-0.30,
        tickers=s1_tickers,
        interventions=(),
        provenance_note=(
            "Synthetic simulation developed during the hackathon window. "
            "No broker connection or live order execution."
        ),
    )
    session_1 = evaluate_cockpit_session(s1_raw, policy)

    s2_tickers = (
        TickerState(
            symbol="AMZN",
            last_price=256.40,
            bid=256.30,
            ask=256.50,
            spread_pct=0.078,
            volume_shares=28_900_000,
            atr=5.10,
            ml_signal=SignalType.BULLISH_TREND,
            ml_confidence=0.81,
            entry_price=256.00,
            stop_loss=252.80,
            profit_target=264.00,
            status="SIMULATED_POSITION",
            shares=31,
            chop_score=72.0,
            projected_exposure_pct=27.78,
        ),
        TickerState(
            symbol="GOOGL",
            last_price=344.20,
            bid=343.80,
            ask=344.60,
            spread_pct=0.232,
            volume_shares=19_800_000,
            atr=5.70,
            ml_signal=SignalType.BULLISH_BREAKOUT,
            ml_confidence=0.74,
            projected_exposure_pct=32.4,
            chop_score=70.0,
            status="SYNTHETIC_CANDIDATE",
        ),
    )

    s2_raw = CockpitSession(
        session_id="sp500-afternoon-rotation",
        title="S&P 500 Afternoon Rotation — 28% Gross Exposure Cap Enforcement",
        description="Fictional simulation of portfolio heat management where excessive gross exposure is deterministically rejected.",
        gross_exposure_pct=27.78,
        max_exposure_cap_pct=28.0,
        daily_drawdown_pct=0.0,
        max_daily_loss_cap_pct=-0.30,
        tickers=s2_tickers,
        interventions=(),
        provenance_note=(
            "Simulated portfolio rotation enforcing a strict 28% gross equity cap. "
            "Newly written during the hackathon event."
        ),
    )
    session_2 = evaluate_cockpit_session(s2_raw, policy)

    return {
        session_1.session_id: session_1,
        session_2.session_id: session_2,
    }


def model_cockpit_evidence(session: CockpitSession) -> Dict[str, Any]:
    """Recompute a minimized model preview from synthetic inputs and the applied policy.

    Local free-text fields and supplied intervention metadata are not transmitted.
    The fixed labels and numeric metrics are synthetic and still require user review.
    """
    _validate_policy(session.applied_policy)
    if (not _valid_number(session.gross_exposure_pct)
            or not _valid_number(session.max_exposure_cap_pct)
            or session.max_exposure_cap_pct != session.applied_policy.max_gross_exposure_pct):
        raise ValueError("Invalid or inconsistent session metrics")

    # Generate every transmitted label ourselves; never forward supplied event IDs,
    # status strings, units, ticker symbols, or free-form reasons.
    canonical = evaluate_cockpit_session(session, session.applied_policy).interventions
    total_candidates = len(session.tickers)
    authorized_count = sum(i.action == GateAction.AUTHORIZED for i in canonical)
    blocked_spread_count = sum(i.action == GateAction.BLOCKED_SPREAD for i in canonical)
    blocked_exposure_count = sum(i.action == GateAction.BLOCKED_EXPOSURE for i in canonical)
    blocked_chop_count = sum(i.action == GateAction.BLOCKED_CHOP for i in canonical)
    blocked_confidence_count = sum(i.action == GateAction.BLOCKED_CONFIDENCE for i in canonical)
    incomplete_count = sum(i.action == GateAction.BLOCKED_INCOMPLETE for i in canonical)

    interventions_summary = [
        {
            "event_id": i.event_id,
            "action": "SIMULATED_PASS" if i.action == GateAction.AUTHORIZED else i.action.value,
            "reason_code": i.reason_code,
            "observed_metric": None if i.action == GateAction.BLOCKED_INCOMPLETE else float(i.observed_metric),
            "limit_metric": None if i.action == GateAction.BLOCKED_INCOMPLETE else float(i.limit_metric),
            "metric_unit": i.metric_unit,
            "status": i.status,
        }
        for i in canonical
    ]

    return {
        "synthetic": True,
        "scope": "SYNTHETIC_COCKPIT_REPLAY",
        "total_candidates": total_candidates,
        "simulated_pass_count": authorized_count,
        "blocked_spread_count": blocked_spread_count,
        "blocked_exposure_count": blocked_exposure_count,
        "blocked_chop_count": blocked_chop_count,
        "blocked_confidence_count": blocked_confidence_count,
        "incomplete_count": incomplete_count,
        "gross_exposure_pct": round(session.gross_exposure_pct, 2),
        "max_exposure_cap_pct": round(session.max_exposure_cap_pct, 2),
        "applied_policy": {
            "max_spread_pct": session.applied_policy.max_spread_pct,
            "max_gross_exposure_pct": session.applied_policy.max_gross_exposure_pct,
            "min_ml_confidence": session.applied_policy.min_ml_confidence,
            "min_chop_score": session.applied_policy.min_chop_score,
        },
        "interventions": interventions_summary,
        "disclaimer": "Fabricated S&P 500 replay simulation. No broker orders, live executions, or dollar savings claimed.",
    }
