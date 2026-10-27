import dataclasses
import json
import threading
import unittest

from auditor.cancellation import (LifecycleError, audit_trace, markdown_report, model_evidence,
                                  parse_trace, sample_traces)
from auditor.cancellation_model import LifecycleSelection, explain_lifecycle
from auditor.jobs import ExplanationJob
from auditor.model import Explanation


def case(name):
    return json.loads(json.dumps(sample_traces()[name]))


def run(value):
    return audit_trace(parse_trace(json.dumps(value)))


def codes(report):
    return {finding.code for finding in report.findings}


class CancellationAuditTests(unittest.TestCase):
    def test_early_release_then_late_fill_retains_historical_violation(self):
        report = run(case('Pending cancel → early release → late fill'))
        self.assertIn('RELEASE_ORDER_NOT_TERMINAL', codes(report))
        self.assertIn('LATE_FILL_AFTER_RELEASE', codes(report))
        event = next(f for f in report.findings if f.code == 'LATE_FILL_AFTER_RELEASE')
        self.assertEqual((event.severity, event.evidence_refs), ('CRITICAL', ('E-004', 'E-005')))
        self.assertEqual((report.current_gate, report.current_reason), ('BLOCK', 'POSITION_RECONCILIATION_REQUIRED'))

    def test_pending_cancel_without_release_does_not_create_a_false_violation(self):
        value = case('Pending cancel → early release → late fill')
        value['events'] = value['events'][:3]
        report = run(value)
        self.assertEqual((report.current_gate, report.current_reason), ('BLOCK', 'ORDER_NOT_TERMINAL'))
        self.assertEqual(report.findings, ())

    def test_later_snapshot_does_not_prove_late_execution(self):
        value = case('Pending cancel → early release → late fill')
        value['events'][4]['type'] = 'BROKER_ORDER'
        del value['events'][4]['broker_event_utc']
        report = run(value)
        self.assertIn('FILL_OBSERVED_AFTER_RELEASE', codes(report))
        self.assertNotIn('LATE_FILL_AFTER_RELEASE', codes(report))

    def test_delayed_broker_event_reports_observation_without_inventing_late_fill(self):
        value = case('Pending cancel → early release → late fill')
        value['events'][4]['broker_event_utc'] = '2026-10-27T14:30:03Z'
        report = run(value)
        self.assertIn('FILL_OBSERVED_AFTER_RELEASE', codes(report))
        self.assertNotIn('LATE_FILL_AFTER_RELEASE', codes(report))

    def test_equal_timestamp_is_not_claimed_as_later(self):
        value = case('Pending cancel → early release → late fill')
        value['events'][4]['broker_event_utc'] = '2026-10-27T14:30:04Z'
        self.assertNotIn('LATE_FILL_AFTER_RELEASE', codes(run(value)))

    def test_confirmed_terminal_zero_fill_passes_only_lifecycle_gate(self):
        report = run(case('Cancel confirmed with zero fill'))
        self.assertEqual((report.current_gate, report.current_reason), ('PASS', 'TERMINAL_ZERO_FILL_CONFIRMED'))
        self.assertEqual(report.findings[0].severity, 'PASS')
        self.assertIn('no broker, order or trade authorization', model_evidence(report)['scope'])

    def test_failed_broker_query_is_unknown_not_zero_or_absent(self):
        report = run(case('Broker query unavailable'))
        self.assertEqual((report.current_gate, report.current_reason), ('BLOCK', 'BROKER_TRUTH_UNKNOWN'))
        self.assertIn('RELEASE_BROKER_TRUTH_UNKNOWN', codes(report))

    def test_later_terminal_confirmation_does_not_erase_early_release(self):
        value = case('Broker query unavailable')
        value['events'].append({'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z',
                                'type': 'BROKER_ORDER', 'status': 'CANCELED', 'cumulative_fill': 0})
        report = run(value)
        self.assertEqual(report.current_gate, 'PASS')
        self.assertIn('RELEASE_BROKER_TRUTH_UNKNOWN', codes(report))
        self.assertTrue(any(f.severity == 'CRITICAL' for f in report.findings))

    def test_partial_fill_needs_fresh_position_and_matching_coverage(self):
        value = case('Partial fill with confirmed protection')
        self.assertEqual(run(value).current_gate, 'PASS')
        del value['events'][4:6]
        report = run(value)
        self.assertEqual(report.current_reason, 'POSITION_RECONCILIATION_REQUIRED')
        self.assertIn('RELEASE_POSITION_RECONCILIATION_REQUIRED', codes(report))

    def test_wrong_or_non_active_protection_does_not_pass(self):
        for status, quantity, reason in [('ACTIVE', 1, 'PROTECTION_QUANTITY_MISMATCH'),
                                         ('PENDING_CANCEL', 2, 'PROTECTION_NOT_CONFIRMED'),
                                         ('UNKNOWN', None, 'PROTECTION_NOT_CONFIRMED')]:
            value = case('Partial fill with confirmed protection')
            value['events'][5]['status'] = status
            value['events'][5]['coverage_qty'] = quantity
            with self.subTest(status=status):
                self.assertEqual(run(value).current_reason, reason)

    def test_old_position_and_protection_are_invalidated_by_new_broker_snapshot(self):
        value = case('Partial fill with confirmed protection')
        # Observe a position/protection while the parent is still partially filled,
        # then receive the terminal snapshot with no fresh position observation.
        value['events'][3] = {'event_id': 'E-004', 'observed_utc': '2026-10-27T14:30:04Z',
                              'type': 'POSITION_OBSERVED', 'position_qty': 2}
        value['events'][4] = {'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z',
                              'type': 'PROTECTION_OBSERVED', 'status': 'ACTIVE', 'coverage_qty': 2}
        value['events'][5] = {'event_id': 'E-006', 'observed_utc': '2026-10-27T14:30:06Z',
                              'type': 'BROKER_ORDER', 'status': 'CANCELED', 'cumulative_fill': 2}
        self.assertEqual(run(value).current_reason, 'POSITION_RECONCILIATION_REQUIRED')

    def test_unknown_after_terminal_requires_new_confirmation(self):
        value = case('Cancel confirmed with zero fill')
        value['events'] = value['events'][:3] + [
            {'event_id': 'E-004', 'observed_utc': '2026-10-27T14:30:04Z', 'type': 'QUERY_FAILED'},
            {'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z', 'type': 'RESERVATION_RELEASED'},
        ]
        report = run(value)
        self.assertEqual(report.current_reason, 'BROKER_TRUTH_UNKNOWN')
        self.assertIn('RELEASE_BROKER_TRUTH_UNKNOWN', codes(report))

    def test_terminal_status_with_missing_fill_quantity_is_unknown(self):
        value = case('Cancel confirmed with zero fill')
        value['events'][2]['cumulative_fill'] = None
        report = run(value)
        self.assertEqual(report.current_reason, 'BROKER_TRUTH_UNKNOWN')
        self.assertIn('RELEASE_BROKER_TRUTH_UNKNOWN', codes(report))

    def test_first_positive_fill_invalidates_older_position_evidence(self):
        value = case('Partial fill with confirmed protection')
        value['events'] = [
            {'event_id': 'E-001', 'observed_utc': '2026-10-27T14:30:01Z', 'type': 'POSITION_OBSERVED', 'position_qty': 0},
            {'event_id': 'E-002', 'observed_utc': '2026-10-27T14:30:02Z', 'type': 'BROKER_ORDER', 'status': 'FILLED', 'cumulative_fill': 2},
            {'event_id': 'E-003', 'observed_utc': '2026-10-27T14:30:03Z', 'type': 'RESERVATION_RELEASED'},
        ]
        report = run(value)
        self.assertEqual(report.current_reason, 'POSITION_RECONCILIATION_REQUIRED')
        self.assertIn('RELEASE_POSITION_RECONCILIATION_REQUIRED', codes(report))

    def test_status_reversal_and_filled_with_zero_are_not_silent_passes(self):
        value = case('Cancel confirmed with zero fill')
        value['events'].append({'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z',
                                'type': 'BROKER_ORDER', 'status': 'NEW', 'cumulative_fill': 0})
        report = run(value)
        self.assertEqual(report.current_reason, 'CONTRADICTORY_BROKER_EVIDENCE')
        value = case('Cancel confirmed with zero fill')
        value['events'][2].update(status='FILLED', cumulative_fill=0)
        report = run(value)
        self.assertIn('FILL_STATUS_WITH_ZERO_QUANTITY', codes(report))
        self.assertEqual(report.current_gate, 'BLOCK')

    def test_decreasing_cumulative_fill_is_reported_as_contradictory(self):
        value = case('Partial fill with confirmed protection')
        value['events'][3]['cumulative_fill'] = 1
        report = run(value)
        self.assertEqual(report.current_gate, 'BLOCK')
        self.assertIn('CONTRADICTORY_BROKER_EVIDENCE', codes(report))

    def test_duplicate_release_is_visible(self):
        value = case('Cancel confirmed with zero fill')
        value['events'].append({'event_id': 'E-005', 'observed_utc': '2026-10-27T14:30:05Z',
                                'type': 'RESERVATION_RELEASED'})
        self.assertIn('DUPLICATE_RESERVATION_RELEASE', codes(run(value)))


class QuoteTests(unittest.TestCase):
    def test_same_report_contains_quote_and_lifecycle_facts(self):
        report = run(case('Pending cancel → early release → late fill'))
        self.assertEqual((report.quote.freshness_status, report.quote.spread_status), ('PASS', 'PASS'))
        self.assertEqual(report.quote.spread_pct, 0.1)
        self.assertIn('RELEASE_ORDER_NOT_TERMINAL', codes(report))
        self.assertEqual(model_evidence(report)['quote']['spread_pct'], 0.1)

    def test_stale_freshness_and_wide_spread_remain_separate(self):
        value = case('Cancel confirmed with zero fill')
        value['quote'].update(bid=99.0, ask=101.0, age_seconds=16.0)
        report = run(value)
        self.assertEqual((report.quote.freshness_status, report.quote.freshness_reason), ('BLOCK', 'QUOTE_STALE'))
        self.assertEqual((report.quote.spread_status, report.quote.spread_pct), ('VETO', 2.0))
        self.assertEqual(report.current_gate, 'PASS')  # Only the separate cancellation gate.

    def test_session_policy_and_missing_quote_never_imply_pass(self):
        value = case('Cancel confirmed with zero fill')
        value['quote']['session'] = 'UNKNOWN'
        report = run(value)
        self.assertEqual(report.quote.freshness_reason, 'SESSION_POLICY_UNKNOWN')
        value['quote'] = None
        self.assertIsNone(run(value).quote)

    def test_crossed_quote_blocks_and_missing_limit_is_unknown(self):
        value = case('Cancel confirmed with zero fill')
        value['quote'].update(bid=102, ask=100)
        self.assertEqual(run(value).quote.spread_reason, 'QUOTE_INVALID_OR_CROSSED')
        value = case('Cancel confirmed with zero fill')
        value['quote']['max_spread_pct'] = None
        self.assertEqual(run(value).quote.spread_status, 'UNKNOWN')

    def test_extended_session_uses_its_own_freshness_limit(self):
        value = case('Cancel confirmed with zero fill')
        value['quote'].update(session='EXTENDED', age_seconds=16.0)
        report = run(value)
        self.assertEqual((report.quote.freshness_status, report.quote.age_limit_seconds), ('PASS', 90.0))


class ExposureTests(unittest.TestCase):
    def test_gross_counts_both_long_and_short_and_heat_is_separate(self):
        result = run(case('Exposure and heat exceed caps')).exposure
        self.assertEqual((result.gross_pct, result.gross_status), (120.0, 'VETO'))
        self.assertEqual((result.heat_pct, result.heat_status), (2.3, 'VETO'))

    def test_equality_at_cap_passes_in_synthetic_policy(self):
        value = case('Exposure and heat exceed caps')
        value['exposure']['gross_cap_pct'] = 120.0
        value['exposure']['heat_cap_pct'] = 2.3
        result = run(value).exposure
        self.assertEqual((result.gross_status, result.heat_status), ('PASS', 'PASS'))

    def test_missing_heat_or_market_values_do_not_mask_other_measure(self):
        value = case('Exposure and heat exceed caps')
        value['exposure']['positions'][0]['risk_to_stop'] = None
        result = run(value).exposure
        self.assertEqual((result.gross_status, result.heat_status, result.heat_pct), ('VETO', 'UNKNOWN', None))
        value = case('Exposure and heat exceed caps')
        value['exposure']['positions'][0]['market_value'] = None
        result = run(value).exposure
        self.assertEqual((result.gross_status, result.gross_pct, result.heat_status), ('UNKNOWN', None, 'VETO'))

    def test_missing_or_zero_equity_never_defaults_to_a_pass(self):
        for equity in (None, 0):
            value = case('Exposure and heat exceed caps')
            value['exposure']['equity'] = equity
            result = run(value).exposure
            self.assertEqual((result.gross_status, result.heat_status), ('UNKNOWN', 'UNKNOWN'))

    def test_extremely_small_equity_is_rejected_without_numeric_overflow(self):
        value = case('Exposure and heat exceed caps')
        value['exposure']['equity'] = 1e-300
        with self.assertRaises(LifecycleError):
            run(value)


class InputAndModelTests(unittest.TestCase):
    def reject(self, value):
        with self.assertRaises(LifecycleError):
            parse_trace(json.dumps(value))

    def test_rejects_non_synthetic_unknown_fields_and_private_identifiers(self):
        value = case('Cancel confirmed with zero fill')
        value['synthetic'] = False
        self.reject(value)
        value = case('Cancel confirmed with zero fill')
        value['events'][0]['account_id'] = 'private-example'
        self.reject(value)
        value = case('Cancel confirmed with zero fill')
        value['events'][0]['event_id'] = 'b10_' + 'X' * 25
        self.reject(value)

    def test_rejects_nonfinite_bool_bad_order_and_duplicate_json_keys(self):
        value = case('Cancel confirmed with zero fill')
        value['events'][0]['cumulative_fill'] = True
        self.reject(value)
        value['events'][0]['cumulative_fill'] = float('inf')
        self.reject(value)
        value = case('Cancel confirmed with zero fill')
        value['events'][1]['observed_utc'] = value['events'][0]['observed_utc']
        self.reject(value)
        value = case('Pending cancel → early release → late fill')
        value['events'][4]['broker_event_utc'] = '2026-10-27T14:30:06Z'
        self.reject(value)
        for raw in ('{"synthetic":true,"synthetic":false}', '{"x":NaN}', b'\xff', b' ' * 65_537):
            with self.subTest(raw=raw[:30]), self.assertRaises(LifecycleError):
                parse_trace(raw)

    def test_untrusted_forged_report_is_not_sent_to_model(self):
        valid = run(case('Cancel confirmed with zero fill'))
        forged = dataclasses.replace(valid, current_reason='PRIVATE-TEXT')
        called = []
        result = explain_lifecycle(forged, LifecycleSelection(), 'fake-key',
                                   transport=lambda *args: called.append(True))
        self.assertEqual((result.status, result.reason), ('UNAVAILABLE', 'INVALID_EVIDENCE'))
        self.assertEqual(called, [])

    def test_trace_identity_changes_when_evidence_changes(self):
        value = case('Cancel confirmed with zero fill')
        first = run(value)
        value['events'][2]['status'] = 'EXPIRED'
        second = run(value)
        self.assertNotEqual(first.trace_id, second.trace_id)
        self.assertEqual(first, run(case('Cancel confirmed with zero fill')))

    def test_only_validated_evidence_is_sent_to_exact_event_model(self):
        report = run(case('Pending cancel → early release → late fill'))
        seen = []
        def transport(url, key, body, timeout):
            seen.append((url, key, body, timeout))
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Synthetic audit explanation.'}}]}
        result = explain_lifecycle(report, LifecycleSelection(), 'fake-secret-key', transport=transport)
        self.assertEqual(result.status, 'AVAILABLE')
        _, _, body, timeout = seen[0]
        self.assertEqual(body['model'], 'meta-models/muse-spark-open-1026')
        self.assertEqual(timeout, 30.0)
        self.assertEqual(json.loads(body['messages'][1]['content']), model_evidence(report))
        self.assertNotIn('fake-secret-key', json.dumps(body))
        self.assertNotIn('account_id', json.dumps(body))

    def test_truncated_model_output_is_not_presented_as_a_success(self):
        report = run(case('Cancel confirmed with zero fill'))
        result = explain_lifecycle(report, LifecycleSelection(), 'fake-key', transport=lambda *args: {
            'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]})
        self.assertEqual((result.status, result.reason, result.text), ('UNAVAILABLE', 'OUTPUT_TRUNCATED', ''))

    def test_background_model_does_not_block_deterministic_audit(self):
        started, release = threading.Event(), threading.Event()
        report = run(case('Broker query unavailable'))
        def slow(*args):
            started.set()
            if not release.wait(2):
                raise TimeoutError('fake')
            return Explanation('AVAILABLE', 'MODEL_EXPLANATION', 'synthetic')
        job = ExplanationJob(worker=slow)
        try:
            self.assertTrue(job.start(report, LifecycleSelection(), 'fake-key'))
            self.assertTrue(started.wait(1))
            self.assertEqual(job.state(report, LifecycleSelection())[0], 'PENDING')
            self.assertEqual(run(case('Cancel confirmed with zero fill')).current_gate, 'PASS')
            release.set()
        finally:
            release.set()
            job.close()
        self.assertEqual(job.state(report, LifecycleSelection())[0], 'DONE')

    def test_report_labels_model_text_as_unverified(self):
        report = run(case('Pending cancel → early release → late fill'))
        result = markdown_report(report, 'Model explanation.')
        self.assertIn('Simulation only', result)
        self.assertIn('LATE_FILL_AFTER_RELEASE', result)
        self.assertIn('Unverified model explanation', result)

    def test_report_marks_missing_quote_and_exposure_as_not_provided(self):
        value = case('Broker query unavailable')
        value['quote'] = None
        result = markdown_report(run(value))
        self.assertIn('Quote input was not provided; no PASS is inferred.', result)
        self.assertIn('Exposure input was not provided; no PASS is inferred.', result)


if __name__ == '__main__':
    unittest.main()
