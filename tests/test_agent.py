"""Agent protocol, executor and single-flight checks with fake transports only."""
from copy import deepcopy
import json
from threading import Event
import subprocess
import sys
from pathlib import Path
import unittest
from unittest import mock

from auditor.agent import ACTIONS, OUTPUT_INSTRUCTION, ActionError, AgentRun, parse_action
from auditor.agent_jobs import AgentJob
from auditor.agent_model import AgentModelError, request_action
from auditor.model import ENDPOINT, MODEL, TransportError
from auditor.agent_transport import agent_post
from tools.run_agent_spike import json_failure_diagnostic, run_spike


def claim(value='PASS', *, field='current_gate'):
    return {'scope': 'gate', 'event_id': None, 'field': field, 'value': value}


def action(name, args=None):
    return json.dumps({'action': name, 'args': {} if args is None else args, 'reason': 'Inspect fictional evidence.'})


def response(text):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}


def scripted_action(context):
    if not context['audit_action_completed']:
        return action('run_lifecycle_audit')
    missing = context['missing_evidence']
    if missing['status'] == 'NEEDS_INPUT':
        return action({'BROKER_ORDER': 'query_order_status', 'POSITION_OBSERVED': 'query_position',
                       'PROTECTION_OBSERVED': 'query_protection'}[missing['event_type']])
    return action('finish_report', {'claims': [claim(context['evidence']['current_gate'])],
                                    'narrative': 'Fictional case; critical history still requires review.'})


class AgentTests(unittest.TestCase):
    def test_valid_run_uses_only_scripted_values_and_preserves_history(self):
        calls = []
        def transport(url, key, body, timeout):
            calls.append(deepcopy(body))
            self.assertEqual((url, timeout, body['model']), (ENDPOINT, 30.0, MODEL))
            self.assertNotIn('tools', body)
            self.assertNotIn(key, json.dumps(body))
            return response(scripted_action(json.loads(body['messages'][1]['content'])))
        run = AgentRun('late_fill')
        before = run.snapshot()['local_memo']['checks']['G03']['critical_history']
        updates = []
        result = run.run(lambda ctx: request_action(ctx, 'NOT_A_PROVIDER_KEY', transport=transport),
                         on_update=lambda value: updates.append(value))
        self.assertEqual(len(calls), 4)
        self.assertEqual(result['status'], 'FINISHED')
        self.assertEqual(result['local_memo']['checks']['G03']['current_status'], 'PASS')
        self.assertEqual(result['local_memo']['checks']['G03']['critical_history'], before)
        self.assertEqual(result['final_report']['claims'][0]['status'], 'EVIDENCE_MATCH')
        self.assertTrue(result['final_report']['review_required'])
        self.assertGreaterEqual(len(updates), 4)
        self.assertEqual([s['action'] for s in result['steps']],
                         ['run_lifecycle_audit', 'query_position', 'query_protection', 'finish_report'])
        self.assertTrue(all(s['validation'] == 'ALLOWED' for s in result['steps']))

    def test_invalid_action_ends_without_running_a_tool(self):
        run = AgentRun('late_fill')
        before = run.snapshot()['local_memo']
        result = run.run(lambda _: action('change_gate', {'gate': 'PASS'}))
        self.assertEqual((result['status'], result['reason']), ('REJECTED', 'INVALID_ACTION'))
        self.assertEqual(result['local_memo'], before)

    def test_model_cannot_supply_snapshot_values_or_change_gate(self):
        for name, args in [('query_position', {'position_qty': 0}),
                           ('run_lifecycle_audit', {'current_gate': 'PASS'}),
                           ('query_protection', {'status': 'ACTIVE', 'coverage_qty': 4})]:
            with self.subTest(name=name):
                run = AgentRun('late_fill')
                before = run.snapshot()['local_memo']
                run.step(action(name, args))
                self.assertEqual(run.reason, 'INVALID_ARGS')
                self.assertEqual(run.snapshot()['local_memo'], before)

    def test_step_limit_caps_requests_without_retry(self):
        calls = []
        run = AgentRun('late_fill', max_steps=1)
        result = run.run(lambda ctx: calls.append(ctx) or action('run_lifecycle_audit'))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['status'], 'STEP_LIMIT')
        self.assertIsNone(result['final_report'])

    def test_all_unavailable_snapshots_stop_needs_input(self):
        for scenario in ('order_unavailable', 'position_unavailable', 'protection_unavailable'):
            with self.subTest(scenario=scenario):
                run = AgentRun(scenario)
                result = run.run(scripted_action)
                self.assertEqual((result['status'], result['reason']),
                                 ('NEEDS_INPUT', 'SCRIPTED_EVIDENCE_UNAVAILABLE'))
                self.assertEqual(result['steps'][-1]['tool_output']['availability'], 'unavailable')
                self.assertIsNone(result['final_report'])

    def test_unknown_order_can_recover_but_critical_history_is_retained(self):
        run = AgentRun('order_recovered')
        result = run.run(scripted_action)
        g03 = result['local_memo']['checks']['G03']
        self.assertEqual(g03['current_status'], 'PASS')
        self.assertTrue(g03['critical_history'])
        self.assertTrue(result['final_report']['review_required'])

    def test_final_report_cannot_skip_missing_evidence(self):
        run = AgentRun('late_fill')
        run.step(action('run_lifecycle_audit'))
        result = run.step(action('finish_report', {'claims': [claim('BLOCK')], 'narrative': 'Unverified.'}))
        self.assertEqual(result['status'], 'NEEDS_INPUT')
        self.assertIsNone(result['final_report'])

    def test_repeated_action_ends_run(self):
        run = AgentRun('late_fill')
        run.step(action('run_lifecycle_audit'))
        result = run.step(action('run_lifecycle_audit'))
        self.assertEqual((result['status'], result['reason']), ('REJECTED', 'REPEATED_ACTION'))

    def test_queries_require_audit_and_matching_missing_evidence(self):
        run = AgentRun('late_fill')
        run.step(action('query_position'))
        self.assertEqual(run.reason, 'AUDIT_REQUIRED')
        run = AgentRun('late_fill')
        run.step(action('run_lifecycle_audit'))
        result = run.step(action('query_protection'))
        self.assertEqual(result['reason'], 'QUERY_NOT_REQUIRED')
        self.assertEqual(len(result['local_memo']['events']), 5)

    def test_claim_contradiction_cannot_change_a_gate(self):
        run = AgentRun('late_fill')
        run.step(action('run_lifecycle_audit'))
        result = run.step(action('compare_claims', {'claims': [claim('PASS')]}))
        self.assertEqual(result['steps'][-1]['tool_output']['claims'][0]['status'], 'CONTRADICTION')
        self.assertEqual(result['local_memo']['checks']['G03']['current_status'], 'BLOCK')

    def test_final_claims_use_existing_verifier_and_narrative_is_unverified(self):
        run = AgentRun('order_recovered')
        run.step(action('run_lifecycle_audit'))
        run.step(action('query_order_status'))
        result = run.step(action('finish_report', {'claims': [claim('BLOCK'), claim('x', field='unsupported')],
                                                  'narrative': '<script>unverified</script>'}))
        self.assertEqual([c['status'] for c in result['final_report']['claims']], ['CONTRADICTION', 'UNVERIFIED'])
        self.assertIn('narrative_unverified', result['final_report'])
        self.assertEqual(result['local_memo']['checks']['G03']['current_status'], 'PASS')

    def test_human_input_stops_without_invented_observations(self):
        run = AgentRun('late_fill')
        run.step(action('run_lifecycle_audit'))
        result = run.step(action('request_human_input'))
        self.assertEqual(result['status'], 'NEEDS_INPUT')
        self.assertEqual(len(result['local_memo']['events']), 5)

    def test_invalid_claim_args_end_run(self):
        for args in ({'claims': []}, {'claims': [claim()], 'gate': 'PASS'},
                     {'claims': [{'scope': 'gate'}]}):
            with self.subTest(args=args):
                run = AgentRun('late_fill')
                run.step(action('run_lifecycle_audit'))
                run.step(action('compare_claims', args))
                self.assertEqual(run.reason, 'INVALID_ARGS')

    def test_strict_json_rejects_ambiguous_or_nonfinite_output(self):
        good = action('run_lifecycle_audit')
        bad = ['Here is JSON: ' + good, good[:-1], '```json\n```json\n' + good + '\n```\n```',
               '{"action":"run_lifecycle_audit","action":"finish_report","args":{},"reason":"x"}',
               '{"action":"query_position","args":{"x":1,"x":2},"reason":"x"}']
        for value in ('NaN', 'Infinity', '-Infinity', '1e999'):
            bad.append('{"action":"query_position","args":{"x":' + value + '},"reason":"x"}')
        for text in bad:
            with self.subTest(text=text):
                run = AgentRun('late_fill')
                result = run.run(lambda _: text)
                self.assertEqual((result['status'], result['reason']), ('REJECTED', 'MALFORMED_JSON'))

    def test_single_outer_json_fence_is_accepted(self):
        text = action('run_lifecycle_audit')
        for wrapped in (text, '```json\n' + text + '\n```', '```\r\n' + text + '\r\n```'):
            self.assertEqual(parse_action(wrapped).action, 'run_lifecycle_audit')

    def test_closed_schema_reason_and_size_limits(self):
        bad = [json.dumps({'action': 'run_lifecycle_audit', 'args': {}, 'reason': 'x', 'extra': True}),
               json.dumps({'action': 'run_lifecycle_audit', 'args': [], 'reason': 'x'}),
               json.dumps({'action': 'run_lifecycle_audit', 'args': {}, 'reason': ''}),
               json.dumps({'action': 'run_lifecycle_audit', 'args': {}, 'reason': 'x' * 501}),
               ' ' * 12001, '[]']
        for text in bad:
            with self.subTest(text=text[:80]), self.assertRaises(ActionError):
                parse_action(text)

    def test_scenario_and_step_limits_are_local(self):
        for value in (0, 9, True, 1.0, '8'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AgentRun('late_fill', max_steps=value)
        with self.assertRaises(ValueError):
            AgentRun('arbitrary private source')

    def test_context_and_snapshot_mutation_cannot_change_local_state(self):
        run = AgentRun('late_fill')
        ctx = run.context(); ctx['evidence']['current_gate'] = 'PASS'
        snap = run.snapshot(); snap['local_memo']['checks']['G03']['current_status'] = 'PASS'
        scripted = run.scripted_snapshots(); scripted['query_position']['position_qty'] = 0
        self.assertEqual(run.context()['evidence']['current_gate'], 'BLOCK')
        self.assertEqual(run.scripted_snapshots()['query_position']['position_qty'], 4)

    def test_previewed_context_matches_first_model_request(self):
        preview = AgentRun('order_unavailable').context()
        def transport(_url, _key, body, _timeout):
            sent = json.loads(body['messages'][1]['content'])
            self.assertEqual(sent, preview)
            self.assertEqual(sent['output_instruction'], OUTPUT_INSTRUCTION)
            self.assertNotIn('tools', body)
            return response(action('run_lifecycle_audit'))
        self.assertEqual(parse_action(request_action(preview, 'sentinel', transport=transport)).action,
                         'run_lifecycle_audit')

    def test_transport_error_is_safe_and_not_retried(self):
        calls = []
        def transport(*args):
            calls.append(args)
            raise TransportError('TIMEOUT')
        run = AgentRun('late_fill')
        result = run.run(lambda ctx: request_action(ctx, 'sentinel', transport=transport))
        self.assertEqual((len(calls), calls[0][-1]), (1, 30.0))
        self.assertEqual(result['status'], 'MODEL_UNAVAILABLE')
        self.assertNotIn('sentinel', json.dumps(result))

    def test_native_tool_call_response_is_not_accepted(self):
        with self.assertRaises(AgentModelError):
            request_action({}, 'sentinel', transport=lambda *args: {
                'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None}}]})

    def test_default_transport_kills_and_drains_timed_out_worker(self):
        child = mock.MagicMock()
        child.__enter__.return_value = child
        child.communicate.side_effect = [subprocess.TimeoutExpired('worker', 30), ('', '')]
        with mock.patch('auditor.agent_transport.subprocess.Popen', return_value=child) as popen:
            with self.assertRaisesRegex(TransportError, 'TIMEOUT'):
                agent_post(ENDPOINT, 'SENSITIVE_KEY_SENTINEL', {}, 30.0)
            child.kill.assert_called_once()
            self.assertEqual(child.communicate.call_count, 2)
            self.assertEqual(child.communicate.call_args_list[0].kwargs['timeout'], 30.0)
            self.assertNotIn('SENSITIVE_KEY_SENTINEL', str(popen.call_args))
            self.assertNotIn('shell', popen.call_args.kwargs)

    def test_worker_result_is_bounded_and_errors_do_not_leak(self):
        for out, error in [('not json', 'INVALID_RESPONSE'),
                           ('{"ok":false,"error":"SENSITIVE_PROVIDER_ERROR"}', 'INVALID_RESPONSE')]:
            with self.subTest(out=out):
                child = mock.MagicMock(returncode=0)
                child.__enter__.return_value = child
                child.communicate.return_value = (out, '')
                with mock.patch('auditor.agent_transport.subprocess.Popen', return_value=child):
                    with self.assertRaisesRegex(TransportError, '^' + error + '$'):
                        agent_post(ENDPOINT, 'sentinel', {}, 30.0)

    def test_worker_returns_structured_response_and_endpoint_is_fixed(self):
        child = mock.MagicMock(returncode=0)
        child.__enter__.return_value = child
        child.communicate.return_value = (json.dumps({'ok': True, 'response': response('x')}), '')
        with mock.patch('auditor.agent_transport.subprocess.Popen', return_value=child) as popen:
            self.assertEqual(agent_post(ENDPOINT, 'sentinel', {}, 30.0), response('x'))
            with self.assertRaises(TransportError):
                agent_post('https://example.invalid', 'sentinel', {}, 30.0)
            self.assertEqual(popen.call_count, 1)

    def test_worker_module_starts_and_rejects_empty_key_without_network(self):
        result = subprocess.run([sys.executable, '-m', 'auditor.agent_transport'],
                                cwd=Path(__file__).resolve().parents[1],
                                input=json.dumps({'api_key': '', 'payload': {}}),
                                text=True, capture_output=True, timeout=5, check=True)
        self.assertEqual(json.loads(result.stdout), {'ok': False, 'error': 'INVALID_RESPONSE'})

    def test_missing_key_does_not_call_provider(self):
        transport = mock.Mock()
        with self.assertRaises(AgentModelError):
            request_action({}, '', transport=transport)
        transport.assert_not_called()

    def test_job_requires_consent_and_is_single_flight(self):
        entered, release = Event(), Event()
        def blocking(*_):
            entered.set()
            self.assertTrue(release.wait(3))
            return action('run_lifecycle_audit')
        job = AgentJob()
        try:
            with mock.patch('auditor.agent_model.request_action', side_effect=blocking) as ask:
                self.assertFalse(job.start('late_fill', 'sentinel', consent=False))
                self.assertFalse(job.start('late_fill', '', consent=True))
                self.assertTrue(job.start('late_fill', 'sentinel', consent=True))
                self.assertTrue(entered.wait(2))
                self.assertFalse(job.start('order_unavailable', 'sentinel', consent=True))
                job.stop(); release.set()
                job._future.result(timeout=3)
                self.assertEqual(ask.call_count, 1)
                self.assertEqual(job.snapshot()[1]['status'], 'CANCELLED')
        finally:
            release.set(); job.close()

    def test_spike_missing_key_is_not_run(self):
        transport = mock.Mock()
        self.assertEqual(run_spike('', transport=transport)['status'], 'NOT_RUN')
        transport.assert_not_called()

    def test_spike_success_and_failure_are_honest_with_fake_transport(self):
        fake = lambda url, key, body, timeout: response(scripted_action(json.loads(body['messages'][1]['content'])))
        receipt = run_spike('sentinel', transport=fake)
        self.assertEqual(receipt['status'], 'GO_PROTOCOL')
        self.assertEqual(len(receipt['cases']), 2)
        bad = mock.Mock(return_value=response('not JSON'))
        receipt = run_spike('sentinel', transport=bad)
        self.assertEqual(receipt['status'], 'NO_GO')
        self.assertEqual(bad.call_count, 1)

    def test_spike_json_diagnostics_classify_without_model_text(self):
        bad_outputs = [
            ('SENSITIVE_MODEL_TEXT ' + action('run_lifecycle_audit'),
             {'error': 'JSON_SYNTAX', 'prefix': 'OTHER', 'position': 'START',
              'prefix_kind': 'TEXT', 'object_marker_later': True}),
            ('{"action":', {'error': 'JSON_SYNTAX', 'prefix': 'OBJECT', 'position': 'END'}),
            ('{"x":1,"x":2}', {'error': 'DUPLICATE_KEY', 'prefix': 'OBJECT'}),
            ('{"x":1e999}', {'error': 'NONFINITE_NUMBER', 'prefix': 'OBJECT'}),
            ('[]', {'error': 'NOT_OBJECT', 'prefix': 'OTHER'}),
            ('```json\n{"x":1}', {'error': 'INVALID_FENCE', 'prefix': 'FENCE'}),
            ('{} trailing', {'error': 'EXTRA_CONTENT', 'prefix': 'OBJECT', 'position': 'MIDDLE'}),
        ]
        for raw, expected in bad_outputs:
            with self.subTest(expected=expected):
                fake = mock.Mock(return_value=response(raw))
                receipt = run_spike('SECRET_KEY_SENTINEL', transport=fake)
                self.assertEqual(receipt['status'], 'NO_GO')
                self.assertEqual(receipt['cases'][0]['reason'], 'MALFORMED_JSON')
                self.assertEqual(receipt['cases'][0]['json_diagnostic'], expected)
                self.assertEqual(fake.call_count, 1)
                self.assertNotIn('SENSITIVE_MODEL_TEXT', json.dumps(receipt))
                self.assertNotIn('SECRET_KEY_SENTINEL', json.dumps(receipt))
        self.assertIsNone(json_failure_diagnostic(action('run_lifecycle_audit')))
        self.assertIsNone(json_failure_diagnostic('```json\n' + action('run_lifecycle_audit') + '\n```'))

    def test_spike_stops_after_first_malformed_second_case_response(self):
        def fake(url, key, body, timeout):
            context = json.loads(body['messages'][1]['content'])
            if context['scenario_id'] == 'order_unavailable':
                return response('<think>SENSITIVE_MODEL_TEXT</think> ' + action('run_lifecycle_audit'))
            return response(scripted_action(context))
        fake = mock.Mock(side_effect=fake)
        receipt = run_spike('SECRET_KEY_SENTINEL', transport=fake)
        self.assertEqual(receipt['status'], 'NO_GO')
        self.assertEqual(receipt['cases'][0]['status'], 'FINISHED')
        self.assertEqual(receipt['cases'][1]['reason'], 'MALFORMED_JSON')
        self.assertEqual(receipt['cases'][1]['actions'], ['INVALID'])
        self.assertEqual(receipt['cases'][1]['json_diagnostic']['prefix_kind'], 'REASONING_TAG')
        self.assertEqual(fake.call_count, 5)
        self.assertNotIn('SENSITIVE_MODEL_TEXT', json.dumps(receipt))
        self.assertNotIn('SECRET_KEY_SENTINEL', json.dumps(receipt))

    def test_spike_schema_rejection_is_not_misreported_as_malformed_json(self):
        raw = json.dumps({'action': 'run_lifecycle_audit', 'args': {},
                          'reason': 'Check', 'extra': 'SENSITIVE_MODEL_TEXT'})
        receipt = run_spike('SECRET_KEY_SENTINEL', transport=lambda *args: response(raw))
        self.assertEqual(receipt['cases'][0]['reason'], 'INVALID_SCHEMA')
        self.assertNotIn('json_diagnostic', receipt['cases'][0])
        self.assertNotIn('SENSITIVE_MODEL_TEXT', json.dumps(receipt))

    def test_failed_diagnostic_does_not_change_rejection(self):
        with mock.patch('tools.run_agent_spike.json_failure_diagnostic', side_effect=RuntimeError('secret')):
            receipt = run_spike('sentinel', transport=lambda *args: response('not JSON'))
        self.assertEqual(receipt['cases'][0]['reason'], 'MALFORMED_JSON')
        self.assertEqual(receipt['cases'][0]['json_diagnostic']['error'], 'DIAGNOSTIC_FAILED')
        self.assertNotIn('secret', json.dumps(receipt))


if __name__ == '__main__':
    unittest.main()
