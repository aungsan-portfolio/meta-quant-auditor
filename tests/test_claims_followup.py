import copy
import json
import unittest
from dataclasses import replace

from auditor.cancellation import audit_trace, parse_trace, sample_traces
from auditor.claims import ClaimsError, example_claims, verify_claims
from auditor.claims_model import ClaimsSelection, generate_claims
from auditor.followup import FollowupError, append_followup, evidence_request
from auditor.jobs import ExplanationJob
from auditor.model import MODEL, Explanation, TransportError


def scenario(name):
    return audit_trace(parse_trace(json.dumps(sample_traces()[name])))


def payload(*claims, interpretation='Unverified interpretation.'):
    return json.dumps({'claims': list(claims), 'interpretation': interpretation})


def claim(scope, event_id, field, value):
    return {'scope': scope, 'event_id': event_id, 'field': field, 'value': value}


class ClaimsBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.report = scenario('Pending cancel → early release → late fill')

    def test_model_event_status_and_timestamp_are_compared_against_exact_evidence(self):
        text = payload(claim('event', 'E-003', 'status', 'PENDING_CANCEL'),
                       claim('event', 'E-003', 'status', 'CANCELED'),
                       claim('event', 'E-005', 'broker_event_utc', '2026-10-27T14:30:05Z'),
                       claim('event', 'E-005', 'observed_utc', '2026-10-27T14:30:04Z'))
        result = verify_claims(self.report, text)
        self.assertEqual([c.status for c in result.claims],
                         ['EVIDENCE_MATCH', 'CONTRADICTION', 'EVIDENCE_MATCH', 'CONTRADICTION'])

    def test_missing_event_missing_time_and_unsupported_interpretation_are_not_verified(self):
        text = payload(claim('event', 'E-9999', 'status', 'CANCELED'),
                       claim('event', 'E-003', 'broker_event_utc', None),
                       claim('event', 'E-003', 'trade_authorized', True),
                       interpretation='The interpretation is never checked by scalar matching.')
        result = verify_claims(self.report, text)
        self.assertEqual([c.status for c in result.claims], ['UNVERIFIED'] * 3)
        self.assertEqual(result.claims[0].reason, 'EVENT_NOT_IN_TRACE')
        self.assertEqual(result.claims[1].reason, 'EVIDENCE_UNKNOWN')
        self.assertNotEqual(result.interpretation, '')

    def test_findings_are_claims_about_the_recorded_audit_not_real_broker_truth(self):
        text = payload(claim('finding', 'E-004', 'code', 'RELEASE_ORDER_NOT_TERMINAL'),
                       claim('finding', 'E-004', 'code', 'RELEASE_TERMINAL_ZERO_FILL_CONFIRMED'))
        result = verify_claims(self.report, text)
        self.assertEqual([c.status for c in result.claims], ['EVIDENCE_MATCH', 'CONTRADICTION'])

    def test_boolean_is_not_a_number_and_missing_exposure_is_unverified(self):
        unknown = scenario('Broker query unavailable')
        result = verify_claims(unknown, payload(claim('quote', None, 'age_seconds', True),
                                                claim('exposure', None, 'gross_status', 'PASS')))
        self.assertEqual([c.status for c in result.claims], ['UNVERIFIED', 'UNVERIFIED'])
        self.assertEqual(result.claims[0].reason, 'INVALID_VALUE_TYPE')
        self.assertEqual(result.claims[1].reason, 'EVIDENCE_UNKNOWN')

    def test_quote_gate_and_exposure_are_independent(self):
        high = scenario('Exposure and heat exceed caps')
        result = verify_claims(high, payload(claim('gate', None, 'current_gate', 'PASS'),
                                              claim('exposure', None, 'gross_status', 'PASS'),
                                              claim('exposure', None, 'heat_status', 'VETO')))
        self.assertEqual([c.status for c in result.claims],
                         ['EVIDENCE_MATCH', 'CONTRADICTION', 'EVIDENCE_MATCH'])

    def test_invalid_empty_duplicate_or_overlong_outputs_never_silently_pass(self):
        invalid = ['not json', '{"claims": [], "interpretation":""}',
                   '{"claims":[],"claims":[],"interpretation":""}',
                   'x' * 12_001,
                   payload(claim('event', 'E-003', 'status', 'PENDING_CANCEL'))[:-1],
                   '{"claims":[{"scope":"quote","event_id":null,"field":"age_seconds","value":NaN}],"interpretation":""}']
        for text in invalid:
            with self.subTest(text=text[:35]):
                with self.assertRaises(ClaimsError):
                    verify_claims(self.report, text)

    def test_claims_with_nested_or_wrong_value_type_never_become_matches(self):
        result = verify_claims(self.report, payload(claim('event', 'E-003', 'status', {'bad': 'PENDING_CANCEL'}),
                                                    claim('event', 'E-003', 'cumulative_fill', False)))
        self.assertEqual([c.status for c in result.claims], ['UNVERIFIED', 'UNVERIFIED'])

    def test_forged_report_is_not_used_for_claim_validation(self):
        forged = replace(self.report, current_gate='PASS')
        with self.assertRaises(ClaimsError):
            verify_claims(forged, payload(claim('gate', None, 'current_gate', 'PASS')))

    def test_offline_example_has_match_contradiction_and_unverified(self):
        for name, source in sample_traces().items():
            with self.subTest(name=name):
                report = audit_trace(parse_trace(json.dumps(source)))
                result = verify_claims(report, example_claims(report))
                self.assertEqual([c.status for c in result.claims],
                                 ['EVIDENCE_MATCH', 'CONTRADICTION', 'UNVERIFIED'])
                self.assertIn('no model was called', result.interpretation)

    def test_real_provider_wrapper_uses_only_event_model_and_no_json_mode(self):
        seen = []
        answer = payload(claim('event', 'E-003', 'status', 'PENDING_CANCEL'))
        def fake_transport(url, key, body, timeout):
            seen.append((url, body, timeout))
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': answer}}]}
        result = generate_claims(self.report, ClaimsSelection(), 'fictional-test-key', transport=fake_transport)
        self.assertEqual(result.status, 'AVAILABLE')
        self.assertEqual(seen[0][1]['model'], MODEL)
        self.assertNotIn('response_format', seen[0][1])
        self.assertEqual(verify_claims(self.report, result.text).claims[0].status, 'EVIDENCE_MATCH')

    def test_provider_timeout_never_changes_deterministic_audit(self):
        def fake_transport(*args):
            raise TransportError('TIMEOUT')
        original = self.report.current_gate, self.report.findings
        result = generate_claims(self.report, ClaimsSelection(), 'fictional-test-key', transport=fake_transport)
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'TIMEOUT'))
        self.assertEqual((self.report.current_gate, self.report.findings), original)

    def test_model_result_is_not_reused_after_a_synthetic_followup(self):
        before = scenario('Broker query unavailable')
        after = audit_trace(parse_trace(append_followup(before, {'status': 'CANCELED', 'cumulative_fill': 0})))
        job = ExplanationJob(worker=lambda report, selection, key: Explanation('AVAILABLE', 'TEST', '{}'))
        try:
            self.assertTrue(job.start(before, ClaimsSelection(), 'fictional-key'))
            status, result = job.state(after, ClaimsSelection())
            self.assertIn(status, ('NOT_STARTED', 'OTHER_PENDING'))
            self.assertIsNone(result)
        finally:
            job.close()


class MissingEvidenceTests(unittest.TestCase):
    def test_broker_query_failure_requests_synthetic_order_and_preserves_critical_history(self):
        before = scenario('Broker query unavailable')
        self.assertEqual(evidence_request(before).status, 'NEEDS_INPUT')
        self.assertEqual(evidence_request(before).event_type, 'BROKER_ORDER')
        raw = append_followup(before, {'status': 'CANCELED', 'cumulative_fill': 0.0})
        after = audit_trace(parse_trace(raw))
        self.assertEqual(after.events[:-1], before.events)
        self.assertEqual(after.current_gate, 'PASS')
        self.assertEqual(evidence_request(after).status, 'REVIEW_REQUIRED')
        self.assertIn('RELEASE_BROKER_TRUTH_UNKNOWN', [f.code for f in after.findings])

    def test_later_unknown_or_nonterminal_status_still_needs_input(self):
        before = scenario('Broker query unavailable')
        for status, fill in [('UNKNOWN', None), ('PENDING_CANCEL', 0)]:
            with self.subTest(status=status):
                after = audit_trace(parse_trace(append_followup(before, {'status': status, 'cumulative_fill': fill})))
                self.assertEqual(evidence_request(after).status, 'NEEDS_INPUT')
                self.assertEqual(after.current_gate, 'BLOCK')

    def test_positive_fill_requests_position_then_coverage_without_erasing_history(self):
        initial = scenario('Pending cancel → early release → late fill')
        self.assertEqual(evidence_request(initial).event_type, 'POSITION_OBSERVED')
        position = audit_trace(parse_trace(append_followup(initial, {'position_qty': 4.0})))
        self.assertEqual(evidence_request(position).event_type, 'PROTECTION_OBSERVED')
        protected = audit_trace(parse_trace(append_followup(position, {'status': 'ACTIVE', 'coverage_qty': 4.0})))
        self.assertEqual(protected.current_gate, 'PASS')
        self.assertEqual(evidence_request(protected).status, 'REVIEW_REQUIRED')
        self.assertIn('LATE_FILL_AFTER_RELEASE', [f.code for f in protected.findings])

    def test_ready_for_lifecycle_review_is_not_a_global_pass(self):
        report = scenario('Exposure and heat exceed caps')
        self.assertEqual(evidence_request(report).status, 'READY_FOR_REVIEW')
        self.assertEqual(report.exposure.gross_status, 'VETO')
        self.assertEqual(report.exposure.heat_status, 'VETO')

    def test_warning_history_requires_review_even_when_current_gate_passes(self):
        source = copy.deepcopy(sample_traces()['Cancel confirmed with zero fill'])
        source['events'].append({'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z',
                                 'type': 'RESERVATION_RELEASED'})
        report = audit_trace(parse_trace(json.dumps(source)))
        self.assertEqual(report.current_gate, 'PASS')
        self.assertIn('DUPLICATE_RESERVATION_RELEASE', [f.code for f in report.findings])
        self.assertEqual(evidence_request(report).status, 'REVIEW_REQUIRED')

    def test_extra_fields_bad_types_or_real_identifiers_are_rejected(self):
        report = scenario('Broker query unavailable')
        for fields in ({'status': 'CANCELED', 'cumulative_fill': 0, 'account_id': 'private'},
                       {'status': 'CANCELED', 'cumulative_fill': True},
                       {'status': 'invalid', 'cumulative_fill': 0},
                       {'status': 'CANCELED', 'cumulative_fill': float('nan')}):
            with self.subTest(fields=fields):
                with self.assertRaises(FollowupError):
                    append_followup(report, fields)

    def test_conflicting_observations_require_manual_review_and_cannot_be_appended_away(self):
        source = copy.deepcopy(sample_traces()['Cancel confirmed with zero fill'])
        source['events'].append({'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z',
                                 'type': 'BROKER_ORDER', 'status': 'NEW', 'cumulative_fill': 0})
        report = audit_trace(parse_trace(json.dumps(source)))
        self.assertEqual(evidence_request(report).status, 'REVIEW_REQUIRED')
        with self.assertRaises(FollowupError):
            append_followup(report, {'status': 'CANCELED', 'cumulative_fill': 0})

    def test_forged_or_already_complete_report_cannot_be_modified(self):
        report = scenario('Cancel confirmed with zero fill')
        with self.assertRaises(FollowupError):
            append_followup(report, {'status': 'CANCELED', 'cumulative_fill': 0})
        with self.assertRaises(FollowupError):
            evidence_request(replace(report, current_gate='BLOCK'))


if __name__ == '__main__':
    unittest.main()
