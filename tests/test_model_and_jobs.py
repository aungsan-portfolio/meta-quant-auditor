import io
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib import error

from auditor.audit import SCENARIOS, evaluate
from auditor.jobs import ExplanationJob
from auditor.model import Explanation, _NoRedirect, _post, explain


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.trace = evaluate(SCENARIOS[0])
        self.finding = self.trace.findings[1]

    def test_completed_response_sends_only_synthetic_evidence(self):
        seen = []

        def transport(url, key, payload, timeout):
            seen.append((url, key, payload, timeout))
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Synthetic G02: VETO.'}}]}

        result = explain(self.trace, self.finding, 'fake-secret-key', transport=transport)
        self.assertEqual((result.status, result.text), ('AVAILABLE', 'Synthetic G02: VETO.'))
        url, key, body, timeout = seen[0]
        self.assertEqual(url, 'https://inference.baseten.co/v1/chat/completions')
        self.assertEqual((body['model'], body['max_tokens'], body['reasoning_effort'], timeout), ('meta-models/muse-spark-open-1026', 1024, 'low', 30.0))
        self.assertEqual(json.loads(body['messages'][1]['content'])['outcome'], 'VETO')
        self.assertNotIn('fake-secret-key', json.dumps(body))

    def test_missing_key_does_not_call_transport(self):
        called = []
        result = explain(self.trace, self.finding, 'your_baseten_api_key_here', transport=lambda *args: called.append(True))
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'KEY_MISSING'))
        self.assertEqual(called, [])

    def test_truncated_output_is_never_presented_as_success(self):
        def transport(*args):
            return {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial', 'reasoning_content': 'private reasoning'}}]}
        result = explain(self.trace, self.finding, 'fake-key', transport=transport)
        self.assertEqual((result.status, result.reason, result.text), ('UNAVAILABLE', 'OUTPUT_TRUNCATED', ''))
        self.assertNotIn('private reasoning', repr(result))

    def test_missing_finish_or_answer_is_not_silently_accepted(self):
        cases = [
            {'choices': [{'message': {'content': 'unknown ending'}}]},
            {'choices': [{'finish_reason': 'stop', 'message': {'content': None, 'reasoning_content': 'private reasoning'}}]},
            {'choices': []},
        ]
        for body in cases:
            with self.subTest(body=body):
                result = explain(self.trace, self.finding, 'fake-key', transport=lambda *args: body)
                self.assertEqual(result.status, 'UNAVAILABLE')
                self.assertEqual(result.text, '')
                self.assertNotIn('private reasoning', repr(result))

    def test_http_failures_are_sanitized_and_redirects_not_followed(self):
        class Opener:
            def __init__(self, code):
                self.code = code
            def open(self, *args, **kwargs):
                raise error.HTTPError('https://invalid.example', self.code, 'secret detail', {}, io.BytesIO(b'private body'))
        for code, reason in ((401, 'ACCESS_DENIED'), (429, 'RATE_LIMITED'), (500, 'HTTP_ERROR')):
            with self.subTest(code=code), patch('urllib.request.build_opener', return_value=Opener(code)) as builder:
                result = explain(self.trace, self.finding, 'fake-key')
                self.assertEqual(result.reason, reason)
                self.assertNotIn('fake-key', repr(result))
                self.assertNotIn('private body', repr(result))
                self.assertIsInstance(builder.call_args.args[0], _NoRedirect)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, None, None, None, 'https://other.example'))

    def test_timeout_does_not_change_the_gate_or_leak_details(self):
        class Opener:
            def open(self, *args, **kwargs):
                raise error.URLError(socket.timeout('fake-private-details'))
        before = self.finding
        with patch('urllib.request.build_opener', return_value=Opener()):
            result = explain(self.trace, self.finding, 'fake-key')
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'TIMEOUT'))
        self.assertEqual(evaluate(SCENARIOS[0]).findings[1], before)
        self.assertNotIn('fake-private-details', repr(result))


class BackgroundJobTests(unittest.TestCase):
    def test_running_model_does_not_block_audit_or_allow_duplicate_request(self):
        started, release = threading.Event(), threading.Event()
        trace = evaluate(SCENARIOS[0])

        def slow_worker(*args):
            started.set()
            if not release.wait(2):
                raise TimeoutError('fake')
            return Explanation('AVAILABLE', 'MODEL_EXPLANATION', 'synthetic')

        job = ExplanationJob(worker=slow_worker)
        try:
            self.assertTrue(job.start(trace, trace.findings[1], 'fake-key'))
            self.assertTrue(started.wait(1))
            self.assertEqual(job.state(trace, trace.findings[1])[0], 'PENDING')
            self.assertFalse(job.start(trace, trace.findings[1], 'fake-key'))
            before = time.monotonic()
            self.assertEqual(evaluate(SCENARIOS[1]).findings[0].outcome, 'BLOCK')
            self.assertLess(time.monotonic() - before, 0.5)
            release.set()
        finally:
            release.set()
            job.close()
        state, answer = job.state(trace, trace.findings[1])
        self.assertEqual((state, answer.status), ('DONE', 'AVAILABLE'))
        other = evaluate(SCENARIOS[2])
        self.assertEqual(job.state(other, other.findings[0]), ('NOT_STARTED', None))
