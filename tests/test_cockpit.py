"""Unit tests for the Autonomous Risk Cockpit and Meta Muse Spark adapter."""
from __future__ import annotations

import math
import unittest

from auditor.cockpit import (
    ALLOWED_REASON_CODES,
    CockpitSession,
    GateAction,
    RiskPolicy,
    SignalType,
    TickerState,
    build_default_sessions,
    evaluate_cockpit_session,
    evaluate_ticker_gate,
    model_cockpit_evidence,
)
from auditor.cockpit_model import CockpitSelection, explain_cockpit


class CockpitTests(unittest.TestCase):
    def setUp(self):
        self.sessions = build_default_sessions()

    def test_default_sessions_are_complete_and_consistent(self):
        self.assertIn("sp500-morning-session", self.sessions)
        self.assertIn("sp500-afternoon-rotation", self.sessions)
        s1 = self.sessions["sp500-morning-session"]

        self.assertLessEqual(s1.gross_exposure_pct, s1.max_exposure_cap_pct)

        # Verify simulated positions have valid bracket stops
        sim_pos = [t for t in s1.tickers if t.status == "SIMULATED_POSITION"]
        self.assertTrue(len(sim_pos) >= 1)
        for pos in sim_pos:
            self.assertIsNotNone(pos.stop_loss)
            self.assertIsNotNone(pos.profit_target)
            self.assertGreater(pos.reward_risk_ratio, 1.5)
            self.assertLess(pos.stop_loss, pos.entry_price)

    def test_dynamic_gate_recalculation(self):
        """Verify gate outcomes dynamically update when inputs change."""
        policy = RiskPolicy(max_spread_pct=0.400, min_chop_score=60.0, max_gross_exposure_pct=28.0)

        # 1. Wide spread initially blocked
        tsla_wide = TickerState(
            symbol="TSLA",
            last_price=254.80,
            bid=252.50,
            ask=257.10,
            spread_pct=1.805,
            volume_shares=65_000_000,
            atr=8.10,
            ml_signal=SignalType.BULLISH_BREAKOUT,
            ml_confidence=0.76,
        )
        res_blocked = evaluate_ticker_gate(tsla_wide, policy)
        self.assertEqual(res_blocked.action, GateAction.BLOCKED_SPREAD)
        self.assertEqual(res_blocked.reason_code, "EXCESS_SPREAD")
        self.assertGreater(res_blocked.metric_excess_delta, 0.0)

        # 2. Tight spread dynamically recalculates to AUTHORIZED
        tsla_tight = TickerState(
            symbol="TSLA",
            last_price=254.80,
            bid=254.75,
            ask=254.85,
            spread_pct=0.039,
            volume_shares=65_000_000,
            atr=8.10,
            ml_signal=SignalType.BULLISH_BREAKOUT,
            ml_confidence=0.76,
            chop_score=70.0,
            projected_exposure_pct=25.0,
        )
        res_ok = evaluate_ticker_gate(tsla_tight, policy)
        self.assertEqual(res_ok.action, GateAction.AUTHORIZED)
        self.assertEqual(res_ok.reason_code, "FOUR_CHECKS_PASS")

        # 3. Chop filter dynamically updates
        aapl_chop = TickerState(
            symbol="AAPL",
            last_price=232.40,
            bid=232.35,
            ask=232.45,
            spread_pct=0.043,
            volume_shares=31_000_000,
            atr=2.90,
            ml_signal=SignalType.CHOP_STANDBY,
            ml_confidence=0.52,
            chop_score=52.0,
        )
        res_chop_blocked = evaluate_ticker_gate(aapl_chop, policy)
        self.assertEqual(res_chop_blocked.action, GateAction.BLOCKED_CHOP)
        self.assertEqual(res_chop_blocked.reason_code, "CHOP_TEXTURE_DETECTED")

        # 4. Exposure cap dynamically updates
        googl_over = TickerState(
            symbol="GOOGL",
            last_price=344.20,
            bid=343.80,
            ask=344.60,
            spread_pct=0.232,
            volume_shares=19_000_000,
            atr=5.70,
            ml_signal=SignalType.BULLISH_BREAKOUT,
            ml_confidence=0.74,
            projected_exposure_pct=32.4,
            chop_score=70.0,
        )
        res_exp_blocked = evaluate_ticker_gate(googl_over, policy)
        self.assertEqual(res_exp_blocked.action, GateAction.BLOCKED_EXPOSURE)
        self.assertEqual(res_exp_blocked.reason_code, "EXPOSURE_CAP_BREACH")

    def test_no_unverified_capital_saved_claims(self):
        """Ensure unprovable dollar savings claims are removed."""
        s1 = self.sessions["sp500-morning-session"]
        for interv in s1.interventions:
            self.assertFalse(hasattr(interv, "capital_saved_dollars"))
            self.assertIn(interv.reason_code, ALLOWED_REASON_CODES)
            self.assertIsInstance(interv.observed_metric, float)
            self.assertIsInstance(interv.limit_metric, float)

        evidence = model_cockpit_evidence(s1)
        self.assertNotIn("total_capital_saved_dollars", evidence)
        self.assertNotIn("capital_saved_dollars", str(evidence))

    def test_data_minimization_and_leakage_resistance(self):
        """Ensure private markers or arbitrary user strings cannot leak to the model."""
        s1 = self.sessions["sp500-morning-session"]
        # Intentionally inject private token into local ticker symbol or provenance note
        private_marker = "SECRET_ACCOUNT_KEY_XYZ_999"
        leaky_tickers = tuple(
            TickerState(
                symbol=f"{t.symbol}_{private_marker}",
                last_price=t.last_price,
                bid=t.bid,
                ask=t.ask,
                spread_pct=t.spread_pct,
                volume_shares=t.volume_shares,
                atr=t.atr,
                ml_signal=t.ml_signal,
                ml_confidence=t.ml_confidence,
                entry_price=t.entry_price,
                stop_loss=t.stop_loss,
                profit_target=t.profit_target,
                status=t.status,
            )
            for t in s1.tickers
        )
        custom_session = CockpitSession(
            session_id="custom-test",
            title=f"Test Session {private_marker}",
            description=f"Local description {private_marker}",
            gross_exposure_pct=s1.gross_exposure_pct,
            max_exposure_cap_pct=s1.max_exposure_cap_pct,
            daily_drawdown_pct=s1.daily_drawdown_pct,
            max_daily_loss_cap_pct=s1.max_daily_loss_cap_pct,
            tickers=leaky_tickers,
            interventions=s1.interventions,
            provenance_note=f"Private note {private_marker}",
        )

        evidence = model_cockpit_evidence(custom_session)
        evidence_str = str(evidence)

        # Private marker must NEVER leak into model evidence
        self.assertNotIn(private_marker, evidence_str)
        self.assertNotIn("account_id", evidence_str.lower())
        self.assertNotIn("api_key", evidence_str.lower())

    def test_invalid_inputs_handled_gracefully(self):
        """Ensure NaN, Inf, and malformed inputs are cleanly validated."""
        policy = RiskPolicy()

        # NaN spread
        nan_ticker = TickerState(
            symbol="NAN_TEST",
            last_price=100.0,
            bid=99.0,
            ask=101.0,
            spread_pct=float("nan"),
            volume_shares=1000,
            atr=1.0,
            ml_signal=SignalType.BULLISH_TREND,
            ml_confidence=0.8,
        )
        with self.assertRaises(ValueError):
            evaluate_ticker_gate(nan_ticker, policy)

        # Adapter returns safe UNAVAILABLE / INVALID_EVIDENCE
        s1 = self.sessions["sp500-morning-session"]
        invalid_session = CockpitSession(
            session_id="nan-session",
            title="Invalid",
            description="Invalid",
            gross_exposure_pct=float("nan"),
            max_exposure_cap_pct=28.0,
            daily_drawdown_pct=0.0,
            max_daily_loss_cap_pct=-0.3,
            tickers=s1.tickers,
            interventions=s1.interventions,
            provenance_note="Test",
        )
        res = explain_cockpit(invalid_session, CockpitSelection(), "valid_key_123")
        self.assertEqual(res.status, "UNAVAILABLE")
        self.assertEqual(res.reason, "INVALID_EVIDENCE")

    def test_cockpit_model_adapter_with_fake_transport(self):
        s1 = self.sessions["sp500-morning-session"]
        selection = CockpitSelection()

        # 1. Missing key
        res_nokey = explain_cockpit(s1, selection, "")
        self.assertEqual(res_nokey.status, "UNAVAILABLE")
        self.assertEqual(res_nokey.reason, "KEY_MISSING")

        # 2. Fake successful transport
        def fake_transport(endpoint, key, payload, timeout):
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "Synthetic risk review: TSLA excess spread (1.805% > 0.400%) blocked by deterministic gate."
                        },
                    }
                ]
            }

        res_ok = explain_cockpit(s1, selection, "test_baseten_key_12345", transport=fake_transport)
        self.assertEqual(res_ok.status, "AVAILABLE")
        self.assertIn("excess spread", res_ok.text)

    def test_cockpit_explanation_job_integration(self):
        """Verify ExplanationJob can manage explain_cockpit background execution."""
        from auditor.jobs import ExplanationJob
        import time

        def fake_worker(session, selection, key):
            return explain_cockpit(
                session, selection, key,
                transport=lambda ep, k, p, to: {
                    "choices": [{"finish_reason": "stop", "message": {"content": "Job completed successfully."}}]
                }
            )

        job = ExplanationJob(worker=fake_worker)
        try:
            s1 = self.sessions["sp500-morning-session"]
            selection = CockpitSelection()
            self.assertEqual(s1.trace_id, s1.session_id)

            started = job.start(s1, selection, "fake_key_123")
            self.assertTrue(started)

            # Wait briefly for thread to finish
            for _ in range(50):
                status, result = job.state(s1, selection)
                if status == "DONE":
                    break
                time.sleep(0.01)

            self.assertEqual(status, "DONE")
            self.assertIsNotNone(result)
            self.assertEqual(result.status, "AVAILABLE")
            self.assertIn("Job completed successfully", result.text)
        finally:
            job.close()


if __name__ == "__main__":
    unittest.main()
