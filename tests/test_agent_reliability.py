"""Independent trial accounting, privacy and no-retry tests using fake transport."""
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from auditor.model import TransportError
from tools.run_agent_reliability import main, run_reliability, source_state


def fake_action(context):
    if not context['audit_action_completed']:
        name, args = 'run_lifecycle_audit', {}
    elif context['missing_evidence']['status'] == 'NEEDS_INPUT':
        name = {'BROKER_ORDER': 'query_order_status', 'POSITION_OBSERVED': 'query_position',
                'PROTECTION_OBSERVED': 'query_protection'}[context['missing_evidence']['event_type']]
        args = {}
    else:
        name, args = 'finish_report', {'claims': [{'scope': 'gate', 'event_id': None,
                                                   'field': 'current_gate',
                                                   'value': context['evidence']['current_gate']}],
                                      'narrative': 'SENSITIVE_MODEL_TEXT'}
    return json.dumps({'action': name, 'args': args, 'reason': 'SENSITIVE_MODEL_TEXT'})


def response(text):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}


class ReliabilityTests(unittest.TestCase):
    def test_three_independent_runs_per_case_are_counted_without_prose(self):
        fake = mock.Mock(side_effect=lambda _url, _key, body, _timeout:
                         response(fake_action(json.loads(body['messages'][1]['content']))))
        receipt = run_reliability('SECRET_KEY_SENTINEL', transport=fake)
        self.assertEqual(receipt['status'], 'COMPLETE')
        self.assertEqual(len(receipt['runs']), 6)
        self.assertEqual(fake.call_count, 18)
        self.assertEqual(receipt['observed_response_origin'], 'UNVERIFIED_OR_CUSTOM')
        self.assertTrue(receipt['all_protocol_compliant'])
        self.assertTrue(receipt['all_expected_paths_passed'])
        self.assertTrue(all('started_at_utc' in r and 'finished_at_utc' in r for r in receipt['runs']))
        for result in receipt['summary'].values():
            self.assertEqual(result, {'planned': 3, 'attempted': 3, 'protocol_compliant': 3,
                                      'protocol_violation': 0, 'protocol_incomplete': 0,
                                      'protocol_undetermined': 0,
                                      'expected_path_pass': 3})
        self.assertTrue(all(r['human_review_required'] for r in receipt['runs']
                            if r['scenario'] == 'late_fill'))
        self.assertTrue(all(r['claim_counts']['EVIDENCE_MATCH'] == 1 for r in receipt['runs']
                            if r['scenario'] == 'late_fill'))
        self.assertNotIn('SECRET_KEY_SENTINEL', json.dumps(receipt))
        self.assertNotIn('SENSITIVE_MODEL_TEXT', json.dumps(receipt))

    def test_failed_run_is_recorded_once_and_later_trials_are_independent(self):
        first = True
        def fake(_url, _key, body, _timeout):
            nonlocal first
            context = json.loads(body['messages'][1]['content'])
            if first:
                first = False
                return response('not JSON')
            return response(fake_action(context))
        fake = mock.Mock(side_effect=fake)
        receipt = run_reliability('sentinel', transport=fake)
        self.assertEqual(receipt['runs'][0]['reason'], 'MALFORMED_JSON')
        self.assertEqual(receipt['runs'][0]['requests_attempted'], 1)
        self.assertEqual(receipt['summary']['late_fill']['protocol_violation'], 1)
        self.assertEqual(receipt['summary']['late_fill']['expected_path_pass'], 2)
        self.assertEqual(receipt['summary']['order_unavailable']['expected_path_pass'], 3)
        self.assertFalse(receipt['all_protocol_compliant'])
        self.assertFalse(receipt['all_expected_paths_passed'])
        self.assertEqual(fake.call_count, 15)

    def test_transport_failures_are_undetermined_not_model_violations(self):
        fake = mock.Mock(side_effect=TransportError('TIMEOUT'))
        receipt = run_reliability('sentinel', transport=fake)
        self.assertEqual(fake.call_count, 6)
        for summary in receipt['summary'].values():
            self.assertEqual(summary['protocol_violation'], 0)
            self.assertEqual(summary['protocol_undetermined'], 3)
            self.assertEqual(summary['expected_path_pass'], 0)

    def test_valid_human_input_is_compliant_but_not_the_scripted_query_path(self):
        def fake(_url, _key, body, _timeout):
            context = json.loads(body['messages'][1]['content'])
            if context['scenario_id'] == 'order_unavailable' and context['audit_action_completed']:
                return response(json.dumps({'action': 'request_human_input', 'args': {}, 'reason': 'Review.'}))
            return response(fake_action(context))
        receipt = run_reliability('sentinel', transport=fake)
        summary = receipt['summary']['order_unavailable']
        self.assertEqual(summary['protocol_compliant'], 3)
        self.assertEqual(summary['protocol_violation'], 0)
        self.assertEqual(summary['expected_path_pass'], 0)
        self.assertTrue(receipt['all_protocol_compliant'])
        self.assertFalse(receipt['all_expected_paths_passed'])

    def test_contradictory_claim_is_counted_not_hidden_by_path_pass(self):
        def fake(_url, _key, body, _timeout):
            context = json.loads(body['messages'][1]['content'])
            if context['scenario_id'] == 'late_fill' and context['missing_evidence']['status'] != 'NEEDS_INPUT':
                value = {'action': 'finish_report', 'args': {'claims': [{'scope': 'gate', 'event_id': None,
                          'field': 'current_gate', 'value': 'BLOCK'}], 'narrative': 'Unverified.'}, 'reason': 'Review.'}
                return response(json.dumps(value))
            return response(fake_action(context))
        receipt = run_reliability('sentinel', transport=fake)
        late = [r for r in receipt['runs'] if r['scenario'] == 'late_fill']
        self.assertTrue(all(r['protocol_and_path_ok'] for r in late))
        self.assertTrue(all(r['claim_counts']['CONTRADICTION'] == 1 for r in late))

    def test_missing_key_and_expired_window_do_not_call_transport(self):
        fake = mock.Mock()
        self.assertEqual(run_reliability('', transport=fake)['reason'], 'KEY_MISSING')
        with mock.patch('tools.run_agent_reliability.WINDOW_SECONDS', 1):
            receipt = run_reliability('sentinel', transport=fake)
        self.assertEqual(receipt['status'], 'INCOMPLETE')
        self.assertEqual(receipt['summary']['late_fill']['attempted'], 0)
        fake.assert_not_called()

    def test_consent_and_unique_output_are_required_before_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'receipt.json'
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(['--output', str(output)])
            output.write_text('keep', encoding='utf-8')
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(['--consent', '--output', str(output)])
            self.assertEqual(output.read_text(encoding='utf-8'), 'keep')

    def test_source_state_never_returns_changed_paths(self):
        head = mock.Mock(stdout='a' * 40 + '\n')
        status = mock.Mock(stdout=' M SENSITIVE_LOCAL_PATH\n')
        with mock.patch('tools.run_agent_reliability.subprocess.run', side_effect=[head, status]):
            source = source_state()
        self.assertEqual(source, {'commit': 'a' * 40, 'working_tree_clean': False})
        self.assertNotIn('SENSITIVE_LOCAL_PATH', json.dumps(source))


if __name__ == '__main__':
    unittest.main()
