import dataclasses
import unittest
from uuid import UUID

from auditor.audit import SCENARIOS, Scenario, evaluate, model_evidence


class SyntheticAuditTests(unittest.TestCase):
    def test_scenario_gate_results_and_freshness_fail_closed(self):
        expected = {
            'wide-spread': ('PASS', 'VETO'),
            'stale-quote': ('BLOCK', 'PASS'),
            'within-limits': ('PASS', 'PASS'),
            'unknown-session': ('BLOCK', 'PASS'),
        }
        for item in SCENARIOS:
            with self.subTest(item=item.slug):
                result = evaluate(item)
                self.assertEqual(tuple(g.outcome for g in result.findings), expected[item.slug])
                self.assertEqual(result, evaluate(item))
                self.assertEqual(str(UUID(result.trace_id)), result.trace_id)
        unknown = evaluate(SCENARIOS[3]).findings[0]
        self.assertEqual((unknown.reason, unknown.limit), ('SESSION_POLICY_UNKNOWN', None))

    def test_invalid_quote_values_fail_closed(self):
        for fields in ({'bid': -1}, {'bid': float('nan')}, {'ask': 1}, {'quote_age_seconds': -1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                evaluate(dataclasses.replace(SCENARIOS[0], **fields))

    def test_session_freshness_policy_is_configurable(self):
        example = Scenario('offhours', 'x', 'x', 99.9, 100.1, 60, 'OFF_HOURS')
        self.assertEqual(evaluate(example).findings[0].outcome, 'PASS')
        self.assertEqual(evaluate(example, freshness_limits={'OFF_HOURS': 20}).findings[0].outcome, 'BLOCK')
        with self.assertRaises(ValueError):
            evaluate(example, freshness_limits={'OFF_HOURS': float('nan')})

    def test_evidence_is_allowlisted_and_forged_trace_is_rejected(self):
        trace = evaluate(SCENARIOS[0])
        evidence = model_evidence(trace, trace.findings[1])
        self.assertEqual(evidence['outcome'], 'VETO')
        self.assertEqual(evidence['event_id'], 'G02')
        self.assertEqual(set(evidence), {'synthetic', 'trace_id', 'event_id', 'observed_utc', 'gate', 'outcome', 'reason_code', 'observed', 'limit', 'unit', 'scope'})
        forged = dataclasses.replace(trace, observed_utc='private-data')
        with self.assertRaises(ValueError):
            model_evidence(forged, forged.findings[1])
