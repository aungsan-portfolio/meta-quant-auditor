"""Real Streamlit script/widget checks; no browser rendering or provider calls."""
import json
from ipaddress import ip_address
import os
from pathlib import Path
import socket
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

from auditor.audit import SCENARIOS
from auditor.jobs import ExplanationJob


ROOT = Path(__file__).resolve().parents[1]
_SOCKET_CONNECT = socket.socket.connect


def loopback_only_connect(sock, address):
    """Windows asyncio creates its socketpair over local TCP, not a provider."""
    try:
        local = (sock.family in (socket.AF_INET, socket.AF_INET6)
                 and isinstance(address, tuple) and ip_address(address[0]).is_loopback)
    except (ValueError, TypeError, IndexError):
        local = False
    if not local:
        raise AssertionError('UI tests must not connect to external services')
    return _SOCKET_CONNECT(sock, address)


class StreamlitPageTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.dict(os.environ, {
            'BASETEN_API_KEY': '', 'PYTHON_DOTENV_DISABLED': '1',
            'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false',
        }))
        self.enterContext(mock.patch.object(socket.socket, 'connect', new=loopback_only_connect))
        self.enterContext(mock.patch.object(socket, 'create_connection',
            side_effect=AssertionError('UI tests must not connect to a provider')))

    def assert_healthy(self, app):
        self.assertEqual([item.message for item in app.exception], [])

    def open_page(self, page=None):
        # Start at the real entrypoint so page_link uses the multipage registry.
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15).run()
        self.addCleanup(self.close_jobs, app)
        self.assert_healthy(app)
        if page:
            app.switch_page(f'pages/{page}').run()
            self.assert_healthy(app)
        return app

    @staticmethod
    def close_jobs(app):
        for key in ('explanation_job', 'workbench_job', 'trace_review_job',
                    'cancellation_job', 'cancellation_claims_job',
                    'paper_event_model_job', 'cockpit_job'):
            if key in app.session_state:
                value = app.session_state[key]
                if isinstance(value, ExplanationJob):
                    value.close()

    @staticmethod
    def button(app, label):
        return next(item for item in app.button if item.label == label)

    def test_network_guard_allows_loopback_and_rejects_external_addresses(self):
        with socket.socket() as listener, socket.socket() as client:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(2)
            client.settimeout(2)
            client.connect(listener.getsockname())
            accepted, _ = listener.accept()
            accepted.close()
        with socket.socket() as probe:
            for address in (('192.0.2.1', 443), ('inference.baseten.co', 443)):
                with self.subTest(address=address):
                    with self.assertRaisesRegex(AssertionError, 'external services'):
                        probe.connect(address)
        with self.assertRaises(AssertionError):
            socket.create_connection(('inference.baseten.co', 443))

    def test_home_quote_scenarios_work_without_an_api_key(self):
        app = self.open_page()
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.slug):
                app.sidebar.radio[0].set_value(scenario).run()
                self.assert_healthy(app)
                self.assertTrue(self.button(app, 'Explain selected event').disabled)

    def test_workbench_builtin_cases_work_without_an_api_key(self):
        app = self.open_page('1_Audit_Workbench.py')
        for case in list(app.selectbox[0].options):
            with self.subTest(case=case):
                app.selectbox[0].set_value(case).run()
                self.assert_healthy(app)
                self.assertTrue(self.button(app, 'Explain full replay').disabled)

    def test_trace_examples_work_without_an_api_key(self):
        app = self.open_page('2_Trace_Inspector.py')
        for case in list(app.selectbox[0].options):
            with self.subTest(case=case):
                app.selectbox[0].set_value(case).run()
                self.assert_healthy(app)
                self.assertTrue(self.button(app, 'Explain trace review').disabled)

    def test_cancellation_cases_and_offline_claim_comparison(self):
        app = self.open_page('3_Cancellation_Safety.py')
        for case in list(app.sidebar.selectbox[0].options):
            with self.subTest(case=case):
                app.sidebar.selectbox[0].set_value(case).run()
                self.assert_healthy(app)
                self.button(app, 'Try fictional claims · no model').click().run()
                self.assert_healthy(app)
                claims = next(item.value for item in app.dataframe if 'Result' in item.value.columns)
                self.assertEqual(claims['Result'].tolist(),
                                 ['EVIDENCE_MATCH', 'CONTRADICTION', 'UNVERIFIED'])
                self.assertTrue(self.button(app, 'Ask Muse Spark for structured claims').disabled)

    def test_paper_page_fictional_replay_and_registered_navigation_link(self):
        app = self.open_page('4_Paper_Observation.py')
        for step in (1, 2, 3):
            with self.subTest(step=step):
                app.slider[0].set_value(step).run()
                self.assert_healthy(app)
                self.assertTrue(self.button(app, 'Ask Muse Spark about this record').disabled)
        self.assertEqual(len(app.get('page_link')), 1)

    def test_cockpit_cap_recalculates_and_syncs_the_evidence_preview(self):
        app = self.open_page('5_Risk_Cockpit.py')
        app.sidebar.radio[0].set_value('sp500-afternoon-rotation').run()
        self.assert_healthy(app)
        self.assertIn('GOOGL — BLOCKED_EXPOSURE', '\n'.join(item.value for item in app.markdown))
        app.sidebar.slider[1].set_value(35.0).run()
        self.assert_healthy(app)
        self.assertIn('GOOGL — SIMULATED_PASS', '\n'.join(item.value for item in app.markdown))
        preview = json.loads(app.get('json')[0].value)
        self.assertEqual(preview['max_exposure_cap_pct'], 35.0)
        self.assertEqual(preview['blocked_exposure_count'], 0)
        self.assertEqual(app.title[0].value, 'Synthetic Risk Cockpit')

    def test_cockpit_consent_resets_when_the_preview_changes(self):
        # A sentinel enables the button; no model button is clicked.
        os.environ['BASETEN_API_KEY'] = 'NOT_A_PROVIDER_CREDENTIAL'
        app = self.open_page('5_Risk_Cockpit.py')
        self.assertTrue(self.button(app, 'Explain synthetic session with Muse Spark').disabled)
        app.checkbox[0].check().run()
        self.assert_healthy(app)
        self.assertFalse(self.button(app, 'Explain synthetic session with Muse Spark').disabled)
        app.sidebar.slider[1].set_value(35.0).run()
        self.assert_healthy(app)
        self.assertFalse(app.checkbox[0].value)
        self.assertTrue(self.button(app, 'Explain synthetic session with Muse Spark').disabled)

    def test_later_cancel_confirmation_does_not_erase_unsafe_history(self):
        app = self.open_page('3_Cancellation_Safety.py')
        app.sidebar.selectbox[0].set_value('Broker query unavailable').run()
        self.assert_healthy(app)
        self.button(app, 'Add fictional follow-up and recheck').click().run()
        self.assert_healthy(app)
        gate = next(item for item in app.metric if item.label == 'G03 · Cancellation')
        self.assertEqual(gate.value, 'CRITICAL HISTORY')
        captions = '\n'.join(item.value for item in app.caption)
        self.assertIn('Current gate: PASS', captions)
        self.assertTrue(any('unsafe release' in item.value for item in app.error))


if __name__ == '__main__':
    unittest.main()
