import copy
import json
import unittest

from auditor.jobs import ExplanationJob
from auditor.model import Explanation
from auditor.trace_review import review_evidence, review_markdown, review_trace
from auditor.workbench import CaseError, parse_case, replay_case, report_evidence, sample_cases
from auditor.workbench_model import WholeReplay, explain_recorded_review


def trace(name):
    case = sample_cases()[name]
    return report_evidence(replay_case(parse_case(json.dumps(case))))


def review(value):
    return review_trace(json.dumps(value))


class TraceReviewTests(unittest.TestCase):
    def test_original_multi_attempt_trace_checks_consistent(self):
        result = review(trace('Duplicate attempt'))
        self.assertEqual(result.status, 'CONSISTENT')
        self.assertTrue(all(item.status == 'CONSISTENT' for item in result.checks))
        self.assertEqual(len(result.replay.attempts), 2)

    def test_false_spread_pass_is_detected_against_observed_and_limit(self):
        value = trace('Wide spread')
        gate = value['attempts'][0]['gates'][1]
        gate['outcome'], gate['reason_code'] = 'PASS', 'WITHIN_SPREAD_LIMIT'
        result = review(value)
        self.assertEqual(result.status, 'REVIEW_REQUIRED')
        self.assertIn('GATE_DISAGREES_WITH_EVIDENCE', {x.code for x in result.checks})
        self.assertIn('DECISION_DISAGREES_WITH_GATES', {x.code for x in result.checks})

    def test_wrong_aggregate_decision_is_not_silently_accepted(self):
        value = trace('Stale quote')
        value['attempts'][0]['decision'] = 'ELIGIBLE'
        result = review(value)
        self.assertEqual(result.status, 'REVIEW_REQUIRED')
        self.assertIn('DECISION_DISAGREES_WITH_GATES', {x.code for x in result.checks})

    def test_missing_required_gate_never_produces_a_consistent_verdict(self):
        value = trace('Duplicate attempt')
        value['attempts'][0]['gates'].pop()
        result = review(value)
        self.assertEqual(result.status, 'INCOMPLETE')
        self.assertIn('MISSING_REQUIRED_GATE', {x.code for x in result.checks})
        self.assertIn('PRIOR_LEDGER_UNCERTAIN', {x.code for x in result.checks})

    def test_duplicate_ledger_disagreement_is_detected(self):
        value = trace('Duplicate attempt')
        gate = value['attempts'][1]['gates'][4]
        gate.update(outcome='PASS', reason_code='NEW_SIMULATION_KEY', observed='NEW')
        value['attempts'][1]['decision'] = 'ELIGIBLE'
        result = review(value)
        self.assertEqual(result.status, 'REVIEW_REQUIRED')
        self.assertIn('DUPLICATE_LEDGER_MISMATCH', {x.code for x in result.checks})

    def test_unknown_session_limit_is_consistent_only_with_a_block(self):
        value = trace('Unknown session')
        self.assertEqual(review(value).status, 'CONSISTENT')
        value['attempts'][0]['gates'][0]['outcome'] = 'PASS'
        self.assertEqual(review(value).status, 'REVIEW_REQUIRED')

    def test_private_or_unrecognized_fields_and_real_label_are_rejected(self):
        for mutation in ('private-field', 'not-synthetic', 'unknown-gate'):
            value = trace('Wide spread')
            if mutation == 'private-field':
                value['attempts'][0]['account_id'] = 'private-example'
            elif mutation == 'not-synthetic':
                value['synthetic'] = False
            else:
                value['attempts'][0]['gates'][0]['gate'] = 'Arbitrary text'
            with self.subTest(mutation=mutation), self.assertRaises(CaseError):
                review(value)

    def test_malformed_and_duplicate_json_is_rejected(self):
        for raw in ('{"synthetic":true,"synthetic":false}', '{"x":NaN}', b'\xff', b' ' * 65_537):
            with self.subTest(raw=raw[:30]), self.assertRaises(CaseError):
                review_trace(raw)

    def test_report_contains_checks_and_unverified_ai_label(self):
        result = review(trace('Wide spread'))
        text = review_markdown(result, 'Example explanation.')
        self.assertIn('Consistency status: **CONSISTENT**', text)
        self.assertIn('not prove', text)
        self.assertIn('unverified', text)

    def test_review_model_receives_only_normalized_facts_and_checks(self):
        result = review(trace('Wide spread'))
        seen = []
        def transport(url, key, body, timeout):
            seen.append(body)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Synthetic explanation.'}}]}
        answer = explain_recorded_review(result, WholeReplay(), 'fake-key', transport=transport)
        self.assertEqual(answer.status, 'AVAILABLE')
        sent = json.loads(seen[0]['messages'][1]['content'])
        self.assertEqual(sent, review_evidence(result))
        self.assertNotIn('fake-key', json.dumps(seen[0]))

    def test_changed_trace_with_same_id_does_not_show_stale_model_response(self):
        original = trace('Wide spread')
        changed = copy.deepcopy(original)
        changed['attempts'][0]['gates'][1]['outcome'] = 'PASS'
        changed['attempts'][0]['gates'][1]['reason_code'] = 'WITHIN_SPREAD_LIMIT'
        first, second = review(original), review(changed)
        self.assertEqual(first.trace_id, second.trace_id)
        self.assertNotEqual(first.job_identity, second.job_identity)
        job = ExplanationJob(worker=lambda *_: Explanation('AVAILABLE', 'MODEL_EXPLANATION', 'old'))
        try:
            self.assertTrue(job.start(first, WholeReplay(), 'fake-key'))
        finally:
            job.close()
        self.assertEqual(job.state(first, WholeReplay())[0], 'DONE')
        self.assertEqual(job.state(second, WholeReplay())[0], 'NOT_STARTED')


if __name__ == '__main__':
    unittest.main()
