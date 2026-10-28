"""Mock UI smoke tests for consent, freshness and untrusted model output."""
import os
from pathlib import Path
import runpy
import sys
import threading
import types
import unittest
from unittest.mock import patch

from auditor.model import Explanation
from auditor.paper_event_model import PAPER_SOURCE, build_evidence


def example(reason='EXCESSIVE_SPREAD'):
    return {'observed_utc': '2026-10-27T14:30:00Z', 'symbol': 'SYN',
            'strategy': 'GAP_AND_GO', 'stage': 'QUOTE_HEALTH',
            'decision': 'REJECT', 'reason': reason}


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
    def __exit__(self, *args):
        return False


class Column:
    def metric(self, *args, **kwargs):
        pass


def fake_streamlit(*, consent, pretend_pressed, initial=None, mode='Local sanitized paper events'):
    st = types.ModuleType('streamlit')
    st.session_state = Session(initial or {})
    st.calls = []
    for name in ('set_page_config', 'title', 'caption', 'info', 'warning', 'error',
                 'dataframe', 'page_link', 'subheader', 'divider', 'json', 'text'):
        setattr(st, name, lambda *args, _name=name, **kwargs: st.calls.append((_name, args, kwargs)))
    st.radio = lambda *args, **kwargs: mode
    st.slider = lambda *args, **kwargs: 3
    st.columns = lambda n: [Column() for _ in range(n)]
    st.fragment = lambda **kwargs: (lambda fn: fn)
    st.expander = lambda *args, **kwargs: Context()
    st.selectbox = lambda label, options, **kwargs: st.session_state[kwargs['key']]
    st.checkbox = lambda *args, **kwargs: consent
    st.button = lambda label, **kwargs: pretend_pressed if label == 'Ask Muse Spark about this record' else False
    st.rerun = lambda *args, **kwargs: None
    return st


class CompletedJob:
    def __init__(self, text):
        self.text = text
    def state(self, evidence, selection):
        return 'DONE', Explanation('AVAILABLE', 'TEST', self.text)


def fake_model_response(evidence, *, altered=None):
    import json
    values = evidence.sent_facts()
    if altered:
        values.update(altered)
    return json.dumps({'claims': [{'field': field, 'value': values[field]}
                                   for field in ('stage', 'decision', 'reason')],
                       'interpretation': 'UNVERIFIED_MODEL_TEXT_SENTINEL'})


class PaperPageTests(unittest.TestCase):
    def run_page(self, *, consent, source_status='POLL_RECENT', pressed=True,
                 reason='EXCESSIVE_SPREAD', initial=None, api_key='FAKE_KEY_SENTINEL',
                 mode='Local sanitized paper events'):
        st = fake_streamlit(consent=consent, pretend_pressed=pressed, initial=initial, mode=mode)
        dotenv = types.ModuleType('dotenv')
        dotenv.load_dotenv = lambda *args, **kwargs: None
        snapshot = {'readable': True, 'checked_utc': '2026-10-27T14:30:02Z',
                    'ignored_records': 0, 'source_tail_only': False, 'events_truncated': False,
                    'events': [example(reason)]}
        started = threading.Event()
        seen = []
        def fake_worker(evidence, selection, key):
            seen.append(evidence.sent_facts())
            started.set()
            return Explanation('AVAILABLE', 'TEST', fake_model_response(evidence))
        with patch.dict(sys.modules, {'streamlit': st, 'dotenv': dotenv}), \
             patch.dict(os.environ, {'BASETEN_API_KEY': api_key}), \
             patch('auditor.paper_observer.read_snapshot', return_value=snapshot), \
             patch('auditor.paper_observer.poll_status', return_value=source_status), \
             patch('auditor.paper_event_model.explain_paper_event', fake_worker):
            runpy.run_path(str(Path('pages/4_Paper_Observation.py')), run_name='__main__')
            if consent and source_status == 'POLL_RECENT' and pressed and initial is None and api_key:
                self.assertTrue(started.wait(1))
        job = st.session_state.get('paper_event_model_job')
        if hasattr(job, 'close'):
            job.close()
        return st, seen

    def test_no_provider_request_without_explicit_consent(self):
        st, seen = self.run_page(consent=False, pressed=True)
        self.assertEqual(seen, [])
        preview = [args[0] for name, args, _ in st.calls if name == 'json']
        self.assertEqual(len(preview), 1)
        self.assertEqual(set(preview[0]), {'source_kind', 'stage', 'decision', 'reason'})
        self.assertNotIn('SYN', str(preview[0]))

    def test_stale_file_cannot_trigger_a_request_even_if_pressed(self):
        _, seen = self.run_page(consent=True, source_status='POLL_STALE', pressed=True)
        self.assertEqual(seen, [])

    def test_no_key_cannot_trigger_a_request_even_if_pressed(self):
        _, seen = self.run_page(consent=True, pressed=True, api_key='')
        self.assertEqual(seen, [])

    def test_confirmed_request_contains_only_minimized_categorical_facts(self):
        _, seen = self.run_page(consent=True, pressed=True)
        self.assertEqual(len(seen), 1)
        self.assertEqual(set(seen[0]), {'source_kind', 'stage', 'decision', 'reason'})
        self.assertNotIn('GAP_AND_GO', str(seen))
        self.assertNotIn('2026-10-27', str(seen))

    def test_synthetic_replay_also_supports_explicit_model_request_without_ledger(self):
        _, seen = self.run_page(consent=True, pressed=True, mode='Fictional replay')
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]['source_kind'], 'SYNTHETIC_REPLAY')
        self.assertEqual(set(seen[0]), {'source_kind', 'stage', 'decision', 'reason'})

    def test_contradictory_model_interpretation_is_not_displayed(self):
        evidence = build_evidence(example(), PAPER_SOURCE)
        job = CompletedJob(fake_model_response(evidence, altered={'decision': 'PASS'}))
        st, _ = self.run_page(consent=False, pressed=False, initial={'paper_event_model_job': job})
        shown_text = ' '.join(str(args) for name, args, _ in st.calls if name == 'text')
        errors = ' '.join(str(args) for name, args, _ in st.calls if name == 'error')
        self.assertNotIn('UNVERIFIED_MODEL_TEXT_SENTINEL', shown_text)
        self.assertIn('interpretation is withheld', errors)

    def test_unknown_source_label_withholds_the_model_interpretation(self):
        evidence = build_evidence(example(reason='OTHER_OR_UNKNOWN'), PAPER_SOURCE)
        job = CompletedJob(fake_model_response(evidence))
        st, _ = self.run_page(consent=False, pressed=False, reason='OTHER_OR_UNKNOWN',
                              initial={'paper_event_model_job': job})
        shown_text = ' '.join(str(args) for name, args, _ in st.calls if name == 'text')
        warnings = ' '.join(str(args) for name, args, _ in st.calls if name == 'warning')
        self.assertNotIn('UNVERIFIED_MODEL_TEXT_SENTINEL', shown_text)
        self.assertIn('interpretation is withheld', warnings)


if __name__ == '__main__':
    unittest.main()
