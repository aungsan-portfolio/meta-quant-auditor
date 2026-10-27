import json
import threading
import unittest

from auditor.jobs import ExplanationJob
from auditor.model import Explanation, TransportError
from auditor.workbench import CaseError, FORMAT, markdown_report, parse_case, replay_case, report_evidence, sample_cases
from auditor.workbench_model import WholeReplay, explain_replay


def sample(name):
    return json.loads(json.dumps(sample_cases()[name]))


def run(case):
    return replay_case(parse_case(json.dumps(case)))


class ReplayTests(unittest.TestCase):
    def test_wide_spread_is_a_veto_with_matching_numerical_evidence(self):
        result = run(sample('Wide spread')).attempts[0]
        spread = result.gates[1]
        self.assertEqual(result.decision, 'VETOED')
        self.assertEqual((spread.outcome, spread.reason_code), ('VETO', 'SPREAD_TOO_WIDE'))
        self.assertEqual((spread.observed, spread.limit), (2.0, 0.4))
        self.assertEqual(result.gates[0].outcome, 'PASS')

    def test_stale_quote_and_unknown_positions_fail_closed(self):
        stale = run(sample('Stale quote')).attempts[0]
        account = run(sample('Unknown account state')).attempts[0]
        self.assertEqual((stale.decision, stale.gates[0].reason_code), ('BLOCKED', 'QUOTE_STALE'))
        self.assertEqual((account.decision, account.gates[2].reason_code), ('BLOCKED', 'POSITIONS_UNKNOWN'))

    def test_unknown_session_never_implies_a_default_freshness_limit(self):
        attempt = run(sample('Unknown session')).attempts[0]
        gate = attempt.gates[0]
        self.assertEqual((attempt.decision, gate.outcome, gate.reason_code, gate.limit),
                         ('BLOCKED', 'BLOCK', 'SESSION_POLICY_UNKNOWN', None))

    def test_session_aware_policy_changes_the_result(self):
        case = sample('Stale quote')
        case['quote']['session'] = 'EXTENDED'
        attempt = run(case).attempts[0]
        self.assertEqual(attempt.gates[0].outcome, 'PASS')
        self.assertEqual(attempt.gates[0].limit, 90.0)
        case['policy']['extended_age_seconds'] = 10
        self.assertEqual(run(case).attempts[0].gates[0].reason_code, 'QUOTE_STALE')

    def test_chase_guard_explains_the_difference_from_planned_entry(self):
        result = run(sample('Excessive chase')).attempts[0]
        chase = result.gates[3]
        self.assertEqual((result.decision, chase.reason_code), ('VETOED', 'CHASE_TOO_LARGE'))
        self.assertGreater(chase.observed, chase.limit)

    def test_duplicate_is_blocked_with_stable_key_and_reproducible_trace(self):
        case = sample('Duplicate attempt')
        one = run(case)
        two = run(case)
        self.assertEqual(one, two)
        first, second = one.attempts
        self.assertEqual((first.decision, second.decision), ('ELIGIBLE', 'BLOCKED'))
        self.assertEqual(first.simulation_key, second.simulation_key)
        self.assertEqual(second.gates[4].reason_code, 'DUPLICATE_ATTEMPT')

    def test_latched_account_blocks_even_when_market_checks_pass(self):
        case = sample('Duplicate attempt')
        case['account']['entries_latched'] = True
        attempt = run(case).attempts[0]
        self.assertEqual((attempt.decision, attempt.gates[2].reason_code), ('BLOCKED', 'ENTRY_LATCHED'))

    def test_displayed_percent_is_the_value_used_for_the_boundary_decision(self):
        case = sample('Wide spread')
        case['policy']['max_spread_percent'] = 2.0
        gate = run(case).attempts[0].gates[1]
        self.assertEqual((gate.observed, gate.limit, gate.outcome), (2.0, 2.0, 'PASS'))
        case['policy']['max_spread_percent'] = 1.999999
        gate = run(case).attempts[0].gates[1]
        self.assertEqual(gate.outcome, 'VETO')
        self.assertGreater(gate.observed, gate.limit)

    def test_report_includes_timeline_and_marks_model_as_unverified(self):
        report = run(sample('Duplicate attempt'))
        text = markdown_report(report, 'Example model explanation.')
        for required in ('Simulation only', 'A-001', 'A-002', 'DUPLICATE_ATTEMPT', 'unverified'):
            self.assertIn(required, text)


class InputBoundaryTests(unittest.TestCase):
    def reject(self, case):
        with self.assertRaises(CaseError):
            parse_case(json.dumps(case))

    def test_real_or_unmarked_cases_are_not_accepted(self):
        case = sample('Wide spread')
        case['synthetic'] = False
        self.reject(case)
        case['synthetic'] = True
        case['format'] = 'another-format'
        self.reject(case)

    def test_unknown_fields_are_rejected_before_any_provider_call(self):
        for location in ('case', 'account', 'attempt'):
            case = sample('Wide spread')
            container = case if location == 'case' else case['account'] if location == 'account' else case['attempts'][0]
            container['account_id'] = 'private-example-value'
            self.reject(case)

    def test_identifiers_cannot_be_free_text_or_a_key(self):
        case = sample('Wide spread')
        case['case_id'] = 'b10_' + 'X' * 24  # synthetic credential-shaped value
        self.reject(case)
        case = sample('Wide spread')
        case['attempts'][0]['candidate_id'] = 'user@example.com'
        self.reject(case)

    def test_duplicate_properties_and_non_finite_numbers_are_rejected(self):
        for text in ('{"synthetic":true,"synthetic":false}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(text=text), self.assertRaises(CaseError):
                parse_case(text)

    def test_invalid_quotes_and_numeric_types_are_rejected(self):
        for field, value in (('bid', -1), ('bid', True), ('ask', 1), ('age_seconds', -1)):
            case = sample('Wide spread')
            case['quote'][field] = value
            with self.subTest(field=field), self.assertRaises(CaseError):
                parse_case(json.dumps(case))

    def test_invalid_time_and_out_of_order_attempts_are_rejected(self):
        case = sample('Duplicate attempt')
        case['attempts'][0]['timestamp_utc'] = '2026-10-27T14:30:00+07:00'
        self.reject(case)
        case = sample('Duplicate attempt')
        case['attempts'][1]['timestamp_utc'] = '2026-10-27T14:29:00Z'
        self.reject(case)

    def test_bounded_size_and_number_of_attempts(self):
        with self.assertRaises(CaseError):
            parse_case(b' ' * 65_537)
        case = sample('Wide spread')
        case['attempts'] = case['attempts'] * 13
        self.reject(case)

    def test_examples_are_valid_and_expose_only_report_fields(self):
        for case in sample_cases().values():
            evidence = report_evidence(run(case))
            self.assertEqual(set(evidence), {'schema', 'synthetic', 'trace_id', 'scope', 'attempts'})
            self.assertTrue(evidence['synthetic'])
            self.assertNotIn('account_id', json.dumps(evidence))
            self.assertNotIn('planned_entry', json.dumps(evidence))
            self.assertNotIn('candidate_id', json.dumps(evidence))


class ReplayModelTests(unittest.TestCase):
    def setUp(self):
        self.report = run(sample('Duplicate attempt'))
        self.selection = WholeReplay()

    def test_only_allowlisted_evidence_is_sent_to_hackathon_model(self):
        seen = []
        def transport(url, key, body, timeout):
            seen.append((url, key, body, timeout))
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Synthetic replay explanation.'}}]}
        result = explain_replay(self.report, self.selection, 'fake-secret-key', transport=transport)
        self.assertEqual(result.status, 'AVAILABLE')
        _, _, payload, timeout = seen[0]
        facts = json.loads(payload['messages'][1]['content'])
        self.assertEqual(payload['model'], 'meta-models/muse-spark-open-1026')
        self.assertEqual(timeout, 30.0)
        self.assertEqual(facts, report_evidence(self.report))
        self.assertNotIn('fake-secret-key', json.dumps(payload))
        self.assertNotIn('candidate_id', json.dumps(facts))

    def test_unfinished_model_output_never_becomes_an_explanation(self):
        for finish in ('length', None):
            result = explain_replay(self.report, self.selection, 'fake-key', transport=lambda *args: {
                'choices': [{'finish_reason': finish, 'message': {'content': 'incomplete'}}]})
            self.assertEqual(result.status, 'UNAVAILABLE')
            self.assertEqual(result.text, '')

    def test_errors_and_missing_keys_do_not_leak_provider_details(self):
        def transport(*args):
            raise TransportError('private-detail')
        self.assertEqual(explain_replay(self.report, self.selection, 'fake-key', transport=transport).reason,
                         'MODEL_UNAVAILABLE')
        result = explain_replay(self.report, self.selection, '', transport=transport)
        self.assertEqual(result.reason, 'KEY_MISSING')

    def test_model_job_does_not_block_replay(self):
        started, release = threading.Event(), threading.Event()
        def slow(*args):
            started.set()
            if not release.wait(2):
                raise TimeoutError('fake')
            return Explanation('AVAILABLE', 'MODEL_EXPLANATION', 'example')
        job = ExplanationJob(worker=slow)
        try:
            self.assertTrue(job.start(self.report, self.selection, 'fake-key'))
            self.assertTrue(started.wait(1))
            self.assertEqual(job.state(self.report, self.selection)[0], 'PENDING')
            self.assertEqual(run(sample('Stale quote')).attempts[0].decision, 'BLOCKED')
            release.set()
        finally:
            release.set()
            job.close()
        self.assertEqual(job.state(self.report, self.selection)[0], 'DONE')


if __name__ == '__main__':
    unittest.main()
