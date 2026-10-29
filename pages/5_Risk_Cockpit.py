"""Streamlit page for the Synthetic Risk Cockpit — Deterministic Gate Replay."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.cockpit import (
    CockpitSession,
    GateAction,
    RiskPolicy,
    build_default_sessions,
    evaluate_cockpit_session,
    model_cockpit_evidence,
)
from auditor.cockpit_model import CockpitSelection, SYSTEM, explain_cockpit
from auditor.jobs import ExplanationJob
from auditor.ui import apply_theme


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)

st.set_page_config(page_title="Synthetic Risk Cockpit", page_icon="🛡️", layout="wide")
apply_theme()
st.title("Synthetic Risk Cockpit")
st.caption("Deterministic pre-trade risk gate evaluation with dynamic threshold recalculation.")
st.info("Synthetic replay simulation only. No live broker connection, real order execution, or dollar savings claimed.")
st.caption("This demo checks four fictional inputs: spread, chop score, projected exposure and confidence. "
           "It does not assess freshness, daily loss, broker protection, or overall paper-trading eligibility.")

default_sessions = build_default_sessions()

with st.sidebar:
    st.subheader("Synthetic Replay Scenario")
    scenario_choice = st.radio(
        "Choose session",
        list(default_sessions.keys()),
        format_func=lambda k: default_sessions[k].title,
    )
    selected_raw = default_sessions[scenario_choice]

    st.divider()
    st.subheader("Dynamic Risk Policy")
    st.caption("Adjust policy limits to see deterministic gates dynamically recalculate in real-time.")

    max_spread = st.slider(
        "Max allowable spread (%)",
        min_value=0.02,
        max_value=2.00,
        value=0.40,
        step=0.01,
        help="Quotes with spread exceeding this limit are deterministically vetoed.",
    )
    max_exposure = st.slider(
        "Max gross portfolio exposure cap (%)",
        min_value=10.0,
        max_value=50.0,
        value=28.0,
        step=1.0,
        help="Trades projecting exposure beyond this cap are blocked.",
    )
    min_confidence = st.slider(
        "Min ML confidence threshold",
        min_value=0.40,
        max_value=0.90,
        value=0.60,
        step=0.05,
    )
    min_chop = st.slider(
        "Min trend chop score",
        min_value=40.0,
        max_value=80.0,
        value=60.0,
        step=5.0,
    )

policy = RiskPolicy(
    max_spread_pct=max_spread,
    min_ml_confidence=min_confidence,
    max_gross_exposure_pct=max_exposure,
    min_chop_score=min_chop,
)

# Dynamically evaluate the session based on interactive policy
session = evaluate_cockpit_session(selected_raw, policy)

# Metrics bar
c1, c2, c3, c4 = st.columns(4)
authorized_count = sum(1 for i in session.interventions if i.action == GateAction.AUTHORIZED)
blocked_count = sum(1 for i in session.interventions if i.action != GateAction.AUTHORIZED)

c1.metric("Simulated candidates", len(session.tickers))
c2.metric("Simulated passing candidates", authorized_count)
c3.metric("Blocked by risk gates", blocked_count)
c4.metric("Gross exposure vs cap", f"{session.gross_exposure_pct:.1f}% / {max_exposure:.1f}%")

st.divider()

left, right = st.columns([1.2, 1], gap="large")

with left:
    st.subheader("01 / Dynamic Gate Evaluations")
    st.caption("Deterministic evaluation results for each synthetic candidate under current risk policy.")

    for interv in session.interventions:
        with st.container(border=True):
            status_color = "🟢" if interv.action == GateAction.AUTHORIZED else "🔴"
            display_action = "SIMULATED_PASS (Within Thresholds)" if interv.action == GateAction.AUTHORIZED else interv.action.value
            delta_unit = "percentage points" if interv.metric_unit == "percent" else interv.metric_unit
            st.markdown(f"**{status_color} {interv.symbol} — {display_action}** (`{interv.event_id}`)")
            st.caption(f"Reason Code: `{interv.reason_code}` · Status: `{interv.status}`")
            if interv.action == GateAction.BLOCKED_INCOMPLETE:
                st.caption("A required synthetic input is missing; this candidate cannot pass.")
            else:
                st.caption(
                    f"Observed: **{interv.observed_metric:.4f} {interv.metric_unit}**  |  "
                    f"Limit: **{interv.limit_metric:.4f} {interv.metric_unit}**  |  "
                    f"Delta: **{interv.metric_excess_delta:+.4f} {delta_unit}**"
                )
            if interv.action == GateAction.AUTHORIZED:
                st.caption("Notice: SIMULATED_PASS represents a synthetic candidate within configured thresholds; not an actual trade authorization or broker order.")
            st.caption(interv.disclaimer)

    with st.expander("Inspect Raw Ticker Data & Bracket Stops"):
        st.dataframe(
            [
                {
                    "Symbol": t.symbol,
                    "Last Price": f"${t.last_price:.2f}",
                    "Spread %": f"{t.spread_pct:.3f}%",
                    "ATR": t.atr,
                    "Signal": t.ml_signal.value,
                    "Confidence": f"{t.ml_confidence:.2f}",
                    "Stop Loss": f"${t.stop_loss:.2f}" if t.stop_loss else "-",
                    "Profit Target": f"${t.profit_target:.2f}" if t.profit_target else "-",
                    "R:R Ratio": f"{t.reward_risk_ratio:.1f}" if t.reward_risk_ratio > 0 else "-",
                    "Scenario role": t.status,
                    "Current gate result": ("SIMULATED_PASS" if i.action == GateAction.AUTHORIZED
                                            else i.action.value),
                }
                for t, i in zip(session.tickers, session.interventions)
            ],
            hide_index=True,
            width="stretch",
        )

with right:
    st.subheader("02 / Meta Muse Spark Explanation")
    st.caption("Live runtime audit call using meta-models/muse-spark-open-1026 on Baseten.")

    evidence = model_cockpit_evidence(session)

    with st.expander("Preview strictly sanitized facts sent to Meta model", expanded=True):
        st.json(evidence)
        st.caption(
            "Data minimization: Sends the previewed synthetic labels and numeric metrics after consent, "
            "along with a fixed instruction. It does not send account balances, broker account IDs, symbols, "
            "or user-supplied free-form strings. "
            "Minimization reduces risk but is not an absolute zero-leakage guarantee."
        )

    with st.expander("Preview the fixed model instruction"):
        st.text(SYSTEM)

    if "cockpit_job" not in st.session_state:
        st.session_state.cockpit_job = ExplanationJob(worker=explain_cockpit)
    job = st.session_state.cockpit_job
    selection = CockpitSelection()

    api_key = os.environ.get("BASETEN_API_KEY", "").strip()
    if not api_key or api_key == "your_baseten_api_key_here":
        st.warning("Set BASETEN_API_KEY in .env to request live explanations. Deterministic gates work offline.")

    status, result = job.state(session, selection)
    busy = status in ("PENDING", "OTHER_PENDING")
    consent = st.checkbox("I reviewed the preview and agree to send these synthetic facts to Baseten.",
                          key=f"cockpit_ack_{session.job_identity}")

    if st.button(
        "Explain synthetic session with Muse Spark",
        type="primary",
        disabled=busy or not consent or not api_key or api_key == "your_baseten_api_key_here",
        width="stretch",
    ):
        if consent and job.start(session, selection, api_key):
            st.rerun()

    if busy:
        st.info("A model request is running. Gate results are unchanged.")
        st.button("Refresh explanation status", key="cockpit_refresh")
    elif status == "DONE" and result is not None:
        if result.status == "AVAILABLE":
            st.warning("Model interpretation is unverified; compare it with the displayed synthetic evidence.")
            st.success("Explanation generated by Meta Muse Spark (Live Runtime):")
            st.text(result.text)
            st.caption(
                "Audit note: Explanation generated from sanitized categorical evidence. "
                "Always verify model text against deterministic boundary numbers."
            )
        else:
            st.error(f"Model explanation unavailable: {result.reason}")
