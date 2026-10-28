import json
import threading
import unittest
from dataclasses import replace

from auditor.jobs import ExplanationJob
from auditor.model import Explanation, TransportError
from auditor.paper_event_model import (PAPER_SOURCE, SYNTHETIC_SOURCE, PaperEvidenceError,
                                       PaperSelection, build_evidence, explain_paper_event,
                                       verify_paper_response)


def event(**changes):
    value = {'observed_utc': '2026-10-27T14:30:00Z', 'symbol': 'SYN',
             'strategy': 'GAP_AND_GO', 'stage': 'QUOTE_HEALTH',
             'decision': 'REJECT', 'reason': 'EXCESSIVE_SPREAD'}
    value.update(changes)
    return value


def response(evidence, *, change=None):
    values = evidence.sent_facts()
    if change:
        values.update(change)
    return json.dumps({'claims': [{'field': k, 'value': values[k]} for k in ('stage', 'decision', 'reason')],
                       'interpretation': 'An unverified interpretation of the reported labels.'})


class PaperEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence(event(), PAPER_SOURCE)

    def test_preview_and_provider_payload_contain_only_four_closed_labels(self):
        calls = []
        def fake_transport(url, key, body, timeout):
            calls.append((url, key, body, timeout))
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': response(self.evidence)}}]}
        result = explain_paper_event(self.evidence, PaperSelection(), 'FAKE_LOCAL_KEY_SENTINEL',
                                     transport=fake_transport)
        self.assertEqual(result.status, 'AVAILABLE')
        url, key, body, timeout = calls[0]
        self.assertEqual((url, body['model'], timeout), ('https://inference.baseten.co/v1/chat/completions',
                                                        'meta-models/muse-spark-open-1026', 30.0))
        sent = json.loads(body['messages'][1]['content'])
        self.assertEqual(sent, self.evidence.sent_facts())
        self.assertEqual(set(sent), {'source_kind', 'stage', 'decision', 'reason'})
        serialized = json.dumps(body)
        for private in ('FAKE_LOCAL_KEY_SENTINEL', '2026-10-27T14:30:00Z', 'SYN', 'GAP_AND_GO',
                        'account_id', 'order_id'):
            # The fixed source label contains SYNTHETIC only in synthetic mode;
            # this test uses the declared-paper mode.
            self.assertNotIn(private, serialized)

    def test_input_with_extra_fields_is_rejected_before_any_call(self):
        with self.assertRaises(PaperEvidenceError):
            build_evidence(event(account_id='PRIVATE_ACCOUNT_SENTINEL'), PAPER_SOURCE)
        with self.assertRaises(PaperEvidenceError):
            build_evidence(event(reason='PRIVATE_KEY_SENTINEL'), PAPER_SOURCE)
        with self.assertRaises(PaperEvidenceError):
            build_evidence(event(), 'UNSUPPORTED_SOURCE')

    def test_forged_evidence_cannot_send_arbitrary_text(self):
        forged = replace(self.evidence, reason='PRIVATE_TOKEN_SENTINEL')
        calls = []
        result = explain_paper_event(forged, PaperSelection(), 'fake-key',
                                     transport=lambda *args: calls.append(args))
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'INVALID_EVIDENCE'))
        self.assertEqual(calls, [])

    def test_recognized_confidence_stage_can_be_verified_without_a_score(self):
        ev = build_evidence(event(stage='CONFIDENCE', reason='CONFIDENCE_BELOW_FLOOR'), PAPER_SOURCE)
        checked = verify_paper_response(ev, response(ev))
        self.assertEqual([c.status for c in checked.claims], ['EVIDENCE_MATCH'] * 3)
        self.assertNotIn('score', ev.sent_facts())
        self.assertNotIn('threshold', ev.sent_facts())

    def test_missing_key_and_provider_failure_do_not_modify_evidence(self):
        calls = []
        result = explain_paper_event(self.evidence, PaperSelection(), 'your_baseten_api_key_here',
                                     transport=lambda *args: calls.append(args))
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'KEY_MISSING'))
        self.assertEqual(calls, [])
        def failed(*args):
            raise TransportError('TIMEOUT')
        result = explain_paper_event(self.evidence, PaperSelection(), 'fake-key', transport=failed)
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'TIMEOUT'))
        self.assertEqual(self.evidence.reason, 'EXCESSIVE_SPREAD')

    def test_truncated_provider_response_is_unavailable(self):
        result = explain_paper_event(self.evidence, PaperSelection(), 'fake-key',
            transport=lambda *args: {'choices': [{'finish_reason': 'length',
                                                   'message': {'content': 'incomplete'}}]})
        self.assertEqual((result.status, result.reason, result.text), ('UNAVAILABLE', 'OUTPUT_TRUNCATED', ''))

    def test_local_identity_changes_for_event_or_source_and_is_not_sent(self):
        alternate = build_evidence(event(symbol='ALT'), PAPER_SOURCE)
        synthetic = build_evidence(event(), SYNTHETIC_SOURCE)
        self.assertNotEqual(self.evidence.trace_id, alternate.trace_id)
        self.assertNotEqual(self.evidence.trace_id, synthetic.trace_id)
        self.assertEqual(self.evidence.sent_facts(), alternate.sent_facts())
        self.assertNotIn(self.evidence.trace_id, json.dumps(self.evidence.sent_facts()))

    def test_job_identity_also_changes_if_valid_sent_labels_change(self):
        altered = replace(self.evidence, decision='PASS')
        self.assertEqual(self.evidence.trace_id, altered.trace_id)
        self.assertNotEqual(self.evidence.job_identity, altered.job_identity)


class PaperClaimVerificationTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence(event(), PAPER_SOURCE)

    def test_exact_labels_match_only_the_reported_fields(self):
        checked = verify_paper_response(self.evidence, response(self.evidence))
        self.assertEqual([c.status for c in checked.claims], ['EVIDENCE_MATCH'] * 3)
        self.assertFalse(checked.has_contradiction)
        self.assertIn('unverified', checked.interpretation)

    def test_contradiction_does_not_change_the_source_event(self):
        checked = verify_paper_response(self.evidence, response(self.evidence, change={'decision': 'PASS'}))
        self.assertTrue(checked.has_contradiction)
        self.assertEqual(checked.claims[1].status, 'CONTRADICTION')
        self.assertEqual(self.evidence.decision, 'REJECT')

    def test_unknown_source_label_is_unverified_even_if_model_guesses(self):
        evidence = build_evidence(event(reason='OTHER_OR_UNKNOWN'), PAPER_SOURCE)
        for value in ('OTHER_OR_UNKNOWN', 'EXCESSIVE_SPREAD'):
            with self.subTest(value=value):
                checked = verify_paper_response(evidence, response(evidence, change={'reason': value}))
                self.assertEqual(checked.claims[2].status, 'UNVERIFIED')
                self.assertFalse(checked.has_contradiction)

    def test_malformed_duplicate_extra_or_missing_fields_are_unavailable(self):
        good = json.loads(response(self.evidence))
        bad = ['not-json', '', '{"claims":[],"claims":[],"interpretation":"x"}',
               json.dumps({**good, 'extra': 1}),
               json.dumps({'claims': good['claims'][:2], 'interpretation': 'x'}),
               json.dumps({'claims': [good['claims'][0]] * 3, 'interpretation': 'x'}),
               json.dumps({'claims': [{**good['claims'][0], 'value': True}, *good['claims'][1:]],
                           'interpretation': 'x'}),
               response(self.evidence)[:-1]]
        for text in bad:
            with self.subTest(text=text[:30]):
                with self.assertRaises(PaperEvidenceError):
                    verify_paper_response(self.evidence, text)

    def test_background_result_is_not_reused_for_another_record_or_mode(self):
        started, release = threading.Event(), threading.Event()
        def worker(*args):
            started.set()
            release.wait(2)
            return Explanation('AVAILABLE', 'TEST', response(self.evidence))
        job = ExplanationJob(worker=worker)
        try:
            self.assertTrue(job.start(self.evidence, PaperSelection(), 'fake-key'))
            self.assertTrue(started.wait(1))
            other = build_evidence(event(symbol='ALT'), PAPER_SOURCE)
            status, result = job.state(other, PaperSelection())
            self.assertEqual((status, result), ('OTHER_PENDING', None))
            release.set()
        finally:
            release.set()
            job.close()
        synthetic = build_evidence(event(), SYNTHETIC_SOURCE)
        self.assertEqual(job.state(synthetic, PaperSelection()), ('NOT_STARTED', None))


if __name__ == '__main__':
    unittest.main()
