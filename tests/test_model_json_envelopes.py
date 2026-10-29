"""Provider formatting must not weaken either structured-claim verifier."""
import json
import unittest

from auditor.cancellation import audit_trace, parse_trace, sample_traces
from auditor.claims import ClaimsError, example_claims, verify_claims
from auditor.paper_event_model import (
    SYNTHETIC_SOURCE, PaperEvidenceError, build_evidence, verify_paper_response,
)


class ModelJSONEnvelopeTests(unittest.TestCase):
    def setUp(self):
        report = audit_trace(parse_trace(json.dumps(
            sample_traces()['Pending cancel → early release → late fill'])))
        evidence = build_evidence({
            'observed_utc': '2026-10-27T14:30:00Z', 'symbol': 'SYN',
            'strategy': 'GAP_AND_GO', 'stage': 'QUOTE_HEALTH',
            'decision': 'REJECT', 'reason': 'EXCESSIVE_SPREAD',
        }, SYNTHETIC_SOURCE)
        paper_text = json.dumps({
            'claims': [{'field': field, 'value': evidence.sent_facts()[field]}
                       for field in ('stage', 'decision', 'reason')],
            'interpretation': 'Unverified text containing a literal ``` marker.',
        })
        self.cases = (
            ('lifecycle', lambda text: verify_claims(report, text),
             ClaimsError, example_claims(report)),
            ('paper', lambda text: verify_paper_response(evidence, text),
             PaperEvidenceError, paper_text),
        )

    def test_single_json_or_unlabelled_fence_preserves_the_exact_result(self):
        for name, verify, _, text in self.cases:
            expected = verify(text)
            for wrapped in (f'```json\n{text}\n```', f'```\n{text}\n```',
                            f' \r\n```JSON\r\n{text}\r\n```\r\n '):
                with self.subTest(workflow=name, wrapped=wrapped[:20]):
                    self.assertEqual(verify(wrapped), expected)

    def test_fence_does_not_promote_contradictions_or_unknown_claims(self):
        for name, verify, _, text in self.cases:
            obj = json.loads(text)
            if name == 'paper':
                obj['claims'][1]['value'] = 'PASS'
            changed = json.dumps(obj)
            baseline = verify(changed)
            self.assertIn('CONTRADICTION', [claim.status for claim in baseline.claims])
            if name == 'lifecycle':
                self.assertIn('UNVERIFIED', [claim.status for claim in baseline.claims])
            with self.subTest(workflow=name):
                self.assertEqual(verify(f'```json\n{changed}\n```'), baseline)

    def test_surrounding_prose_is_not_searched_for_embedded_json(self):
        for name, verify, error, text in self.cases:
            for answer in (f'Here is the JSON:\n{text}', f'{text}\nExplanation follows.',
                           f'Here is the JSON:\n```json\n{text}\n```',
                           f'```json\n{text}\n```\nExplanation follows.'):
                with self.subTest(workflow=name, answer=answer[:20]):
                    with self.assertRaises(error):
                        verify(answer)

    def test_multiple_nested_malformed_or_other_language_fences_are_rejected(self):
        for name, verify, error, text in self.cases:
            for answer in (f'```json\n{text}', f'```json\n{text}\n````',
                           f'```javascript\n{text}\n```', f'```json {text}```',
                           f'```json\n{text}\n```\n```json\n{text}\n```',
                           f'```json\n```json\n{text}\n```\n```'):
                with self.subTest(workflow=name, answer=answer[:20]):
                    with self.assertRaises(error):
                        verify(answer)

    def test_duplicate_properties_inside_fences_are_still_rejected(self):
        for name, verify, error, text in self.cases:
            for malformed in (text.replace('"claims":', '"claims": [], "claims":', 1),
                              text.replace('"value":', '"value": "x", "value":', 1)):
                with self.subTest(workflow=name):
                    with self.assertRaises(error):
                        verify(f'```json\n{malformed}\n```')

    def test_nonfinite_numbers_inside_fences_are_still_rejected(self):
        for name, verify, error, text in self.cases:
            for value in (float('nan'), float('inf'), -float('inf')):
                obj = json.loads(text)
                obj['claims'][0]['value'] = value
                with self.subTest(workflow=name, value=value):
                    with self.assertRaises(error):
                        verify(f'```json\n{json.dumps(obj)}\n```')

    def test_closed_schemas_still_reject_extra_and_missing_fields(self):
        for name, verify, error, text in self.cases:
            extra = json.loads(text)
            extra['unexpected'] = 'not allowed'
            missing = json.loads(text)
            del missing['claims'][0]['value']
            extra_claim = json.loads(text)
            extra_claim['claims'][0]['unexpected'] = 'not allowed'
            for obj in (extra, missing, extra_claim):
                with self.subTest(workflow=name):
                    with self.assertRaises(error):
                        verify(f'```json\n{json.dumps(obj)}\n```')

    def test_complete_fence_does_not_repair_truncated_json(self):
        for name, verify, error, text in self.cases:
            with self.subTest(workflow=name):
                with self.assertRaises(error):
                    verify(f'```json\n{text[:-1]}\n```')

    def test_original_response_size_limit_includes_the_fence(self):
        for name, verify, error, text in self.cases:
            padded = text + ' ' * (12_000 - len(text))
            with self.subTest(workflow=name):
                self.assertEqual(verify(padded), verify(text))
                with self.assertRaises(error):
                    verify(f'```json\n{padded}\n```')

    def test_rejected_output_is_not_echoed_in_errors(self):
        sentinel = 'MODEL_OUTPUT_PRIVATE_SENTINEL'
        for name, verify, error, text in self.cases:
            with self.subTest(workflow=name):
                with self.assertRaises(error) as raised:
                    verify(f'{sentinel}\n```json\n{text}\n```')
                self.assertNotIn(sentinel, str(raised.exception))

    def test_non_text_inputs_are_rejected(self):
        for name, verify, error, _ in self.cases:
            for value in (None, b'{}', {}, []):
                with self.subTest(workflow=name, value=value):
                    with self.assertRaises(error):
                        verify(value)


if __name__ == '__main__':
    unittest.main()
