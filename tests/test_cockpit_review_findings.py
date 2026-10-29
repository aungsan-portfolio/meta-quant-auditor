"""Regression checks for the independently reviewed synthetic cockpit."""
from dataclasses import replace
import json
import unittest

from auditor.cockpit import (
    GateAction, RiskPolicy, build_default_sessions, evaluate_cockpit_session,
    evaluate_ticker_gate, model_cockpit_evidence,
)
from auditor.cockpit_model import CockpitSelection, explain_cockpit
from auditor.jobs import ExplanationJob
from auditor.model import Explanation


class CockpitReviewFindings(unittest.TestCase):
    def setUp(self):
        self.sessions = build_default_sessions()

    def test_model_preview_uses_current_exposure_cap(self):
        initial = self.sessions['sp500-afternoon-rotation']
        current = evaluate_cockpit_session(initial, RiskPolicy(max_gross_exposure_pct=35.0))
        googl = next(i for i in current.interventions if i.symbol == 'GOOGL')
        self.assertEqual(googl.action, GateAction.AUTHORIZED)
        self.assertEqual(current.max_exposure_cap_pct, 35.0)
        self.assertEqual(model_cockpit_evidence(current)['max_exposure_cap_pct'], 35.0)

    def test_arbitrary_intervention_strings_never_reach_evidence(self):
        session = self.sessions['sp500-morning-session']
        marker = 'TEST_PRIVATE_INTERVENTION_MARKER'
        for field in ('event_id', 'metric_unit', 'status'):
            intervention = replace(session.interventions[0], **{field: marker})
            modified = replace(session, interventions=(intervention,) + session.interventions[1:])
            with self.subTest(field=field):
                self.assertNotIn(marker, str(model_cockpit_evidence(modified)))

    def test_old_model_output_is_not_reused_after_policy_change(self):
        initial = self.sessions['sp500-afternoon-rotation']
        current = evaluate_cockpit_session(initial, RiskPolicy(max_gross_exposure_pct=35.0))
        job = ExplanationJob(worker=lambda *_: Explanation('AVAILABLE', 'OK', 'old-output'))
        selection = CockpitSelection()
        try:
            self.assertTrue(job.start(initial, selection, 'FAKE_KEY'))
            job._future.result(timeout=3)
            self.assertEqual(job.state(current, selection), ('NOT_STARTED', None))
        finally:
            job.close()

    def test_invalid_policy_cannot_produce_a_pass(self):
        ticker = self.sessions['sp500-morning-session'].tickers[0]
        for policy in (
            RiskPolicy(max_spread_pct=float('nan')),
            RiskPolicy(max_gross_exposure_pct=float('inf')),
            RiskPolicy(min_ml_confidence=-0.01),
            RiskPolicy(min_chop_score=101.0),
        ):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                evaluate_ticker_gate(ticker, policy)

    def test_missing_required_inputs_are_not_a_pass(self):
        ticker = self.sessions['sp500-morning-session'].tickers[0]
        for changed in (replace(ticker, chop_score=None),
                        replace(ticker, projected_exposure_pct=None)):
            with self.subTest(ticker=changed):
                self.assertEqual(evaluate_ticker_gate(changed).action, GateAction.BLOCKED_INCOMPLETE)

    def test_relaxing_spread_does_not_bypass_other_checks(self):
        ticker = next(t for t in self.sessions['sp500-morning-session'].tickers if t.symbol == 'TSLA')
        ticker = replace(ticker, projected_exposure_pct=40.0, ml_confidence=0.50)
        policy = RiskPolicy(max_spread_pct=2.0)
        self.assertEqual(evaluate_ticker_gate(ticker, policy).action, GateAction.BLOCKED_EXPOSURE)
        ticker = replace(ticker, projected_exposure_pct=20.0)
        self.assertEqual(evaluate_ticker_gate(ticker, policy).action, GateAction.BLOCKED_CONFIDENCE)

    def test_fake_provider_receives_exact_preview(self):
        session = evaluate_cockpit_session(self.sessions['sp500-afternoon-rotation'],
                                           RiskPolicy(max_gross_exposure_pct=35.0))
        seen = []
        def fake_transport(_endpoint, _key, payload, _timeout):
            seen.append(payload)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'synthetic'}}]}
        result = explain_cockpit(session, CockpitSelection(), 'fake_key', transport=fake_transport)
        self.assertEqual(result.status, 'AVAILABLE')
        self.assertEqual(json.loads(seen[0]['messages'][1]['content']), model_cockpit_evidence(session))


if __name__ == '__main__':
    unittest.main()
