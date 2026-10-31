"""Agent preview/consent and live-updating widget checks; fake provider only."""
import json
import os
from pathlib import Path
import socket
import time
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest
from test_streamlit_pages import loopback_only_connect


ROOT = Path(__file__).resolve().parents[1]


def fake_transport(url, key, body, timeout):
    ctx = json.loads(body['messages'][1]['content'])
    if not ctx['audit_action_completed']:
        name, args = 'run_lifecycle_audit', {}
    elif ctx['missing_evidence']['status'] == 'NEEDS_INPUT':
        name = {'BROKER_ORDER': 'query_order_status', 'POSITION_OBSERVED': 'query_position',
                'PROTECTION_OBSERVED': 'query_protection'}[ctx['missing_evidence']['event_type']]
        args = {}
    else:
        name, args = 'finish_report', {'claims': [{'scope': 'gate', 'event_id': None,
                                                  'field': 'current_gate', 'value': ctx['evidence']['current_gate']}],
                                     'narrative': 'Fake transport narration.'}
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(
        {'action': name, 'args': args, 'reason': 'Fictional evidence review.'})}}]}


class AgentPageTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ, {'BASETEN_API_KEY': '', 'PYTHON_DOTENV_DISABLED': '1',
                                                       'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false'}))
        self.enterContext(mock.patch.object(socket.socket, 'connect', new=loopback_only_connect))
        self.enterContext(mock.patch.object(socket, 'create_connection', side_effect=AssertionError('No provider calls')))

    def open(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15).run()
        app.switch_page('pages/6_Auditor_Agent.py').run()
        self.addCleanup(lambda: app.session_state['auditor_agent_job'].close())
        self.assertEqual(list(app.exception), [])
        return app

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_preview_and_consent_do_not_request_a_model(self):
        with mock.patch('auditor.agent_model._post') as post:
            app = self.open()
            self.assertFalse(any(b.label == 'Run consented agent' for b in app.button))
            self.button(app, 'Start agent').click().run()
            self.assertGreaterEqual(len(app.get('json')), 2)
            self.assertTrue(self.button(app, 'Run consented agent').disabled)
            app.checkbox[0].check().run()
            self.assertTrue(self.button(app, 'Run consented agent').disabled)  # no key
            post.assert_not_called()

    def test_new_scenario_needs_its_own_preview_and_consent(self):
        os.environ['BASETEN_API_KEY'] = 'NOT_A_PROVIDER_CREDENTIAL'
        app = self.open()
        self.button(app, 'Start agent').click().run()
        app.checkbox[0].check().run()
        self.assertFalse(self.button(app, 'Run consented agent').disabled)
        app.selectbox[0].set_value('order_unavailable').run()
        self.assertFalse(any(b.label == 'Run consented agent' for b in app.button))
        self.button(app, 'Start agent').click().run()
        self.assertFalse(app.checkbox[0].value)

    def test_background_run_displays_completed_trace_with_fake_transport(self):
        os.environ['BASETEN_API_KEY'] = 'NOT_A_PROVIDER_CREDENTIAL'
        with mock.patch('auditor.agent_model._post', side_effect=fake_transport) as post:
            app = self.open()
            self.button(app, 'Start agent').click().run()
            app.checkbox[0].check().run()
            self.button(app, 'Run consented agent').click().run()
            job = app.session_state['auditor_agent_job']
            deadline = time.monotonic() + 5
            while job.snapshot()[0] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(job.snapshot()[0])
            app.run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(post.call_count, 4)
            self.assertTrue(any('FINISHED' in item.value for item in app.markdown))
            self.assertEqual(len(job.snapshot()[1]['steps']), 4)
            self.assertTrue(any('unverified' in item.value.lower() for item in app.warning))


if __name__ == '__main__':
    unittest.main()
