"""Mocked Streamlit checks; no browser or live provider is used."""
import os
from pathlib import Path
import runpy
import sys
import threading
import types
import unittest
from unittest.mock import patch

from auditor.cockpit import model_cockpit_evidence
from auditor.model import Explanation


class Session(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


class Context:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def metric(self, *args, **kwargs):
        pass


def make_streamlit(*, consent, exposure):
    st = types.ModuleType('streamlit')
    st.session_state = Session()
    st.sidebar = Context()
    st.previews = []
    st.checkbox_keys = []
    st.buttons = []
    for name in ('set_page_config', 'title', 'caption', 'info', 'warning', 'error',
                 'dataframe', 'subheader', 'divider', 'text', 'markdown', 'success', 'write'):
        setattr(st, name, lambda *args, **kwargs: None)
    st.radio = lambda *args, **kwargs: 'sp500-afternoon-rotation'
    st.slider = lambda label, **kwargs: exposure if label == 'Max gross portfolio exposure cap (%)' else kwargs['value']
    st.columns = lambda spec, **kwargs: [Context() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.expander = lambda *args, **kwargs: Context()
    st.container = lambda *args, **kwargs: Context()
    st.json = lambda value: st.previews.append(value)
    def checkbox(*args, **kwargs):
        st.checkbox_keys.append(kwargs['key'])
        return consent
    st.checkbox = checkbox
    def button(label, **kwargs):
        st.buttons.append((label, kwargs))
        # Deliberately simulate a press even when disabled: the page must check consent itself.
        return label == 'Explain synthetic session with Muse Spark'
    st.button = button
    st.rerun = lambda: None
    return st


class CockpitPageReview(unittest.TestCase):
    def run_page(self, *, consent, exposure):
        st = make_streamlit(consent=consent, exposure=exposure)
        dotenv = types.ModuleType('dotenv')
        dotenv.load_dotenv = lambda *args, **kwargs: None
        seen = []
        started = threading.Event()
        def worker(session, _selection, _key):
            seen.append(model_cockpit_evidence(session))
            started.set()
            return Explanation('AVAILABLE', 'TEST', 'fictional response')
        with patch.dict(sys.modules, {'streamlit': st, 'dotenv': dotenv}), \
             patch.dict(os.environ, {'BASETEN_API_KEY': 'fake_test_key'}, clear=True), \
             patch('auditor.cockpit_model.explain_cockpit', worker):
            runpy.run_path(str(Path('pages/5_Risk_Cockpit.py')), run_name='__main__')
            if consent:
                self.assertTrue(started.wait(1))
        st.session_state.cockpit_job.close()
        return st, seen

    def test_no_request_without_consent_even_if_button_is_spoofed(self):
        st, sent = self.run_page(consent=False, exposure=28.0)
        self.assertEqual(sent, [])
        button = next(kwargs for label, kwargs in st.buttons if label.startswith('Explain synthetic'))
        self.assertTrue(button['disabled'])

    def test_preview_matches_request_and_consent_changes_with_policy(self):
        before, _ = self.run_page(consent=False, exposure=28.0)
        after, sent = self.run_page(consent=True, exposure=35.0)
        self.assertEqual(sent, after.previews)
        self.assertEqual(sent[0]['max_exposure_cap_pct'], 35.0)
        self.assertNotEqual(before.checkbox_keys, after.checkbox_keys)


if __name__ == '__main__':
    unittest.main()
