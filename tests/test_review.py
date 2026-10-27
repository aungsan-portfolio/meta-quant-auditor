import copy
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from auditor.cancellation import audit_trace, parse_trace, sample_traces
from auditor.review import (ReviewError, build_memo, record_review, review_download,
                            validate_memo)


def audited(name):
    return audit_trace(parse_trace(json.dumps(sample_traces()[name])))


class SyntheticReviewTests(unittest.TestCase):
    def setUp(self):
        self.report = audited('Pending cancel → early release → late fill')
        self.memo = build_memo(self.report)
        self.time = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)

    def record(self, decision='REVIEWED', *, evidence=True, scope=True):
        return record_review(self.report, self.memo, decision,
                             evidence_acknowledged=evidence,
                             scope_acknowledged=scope, now=self.time)

    def test_memo_retains_critical_history_and_event_references(self):
        check = self.memo['checks']['G03']
        findings = {item['code']: item for item in check['critical_history']}
        self.assertIn('RELEASE_ORDER_NOT_TERMINAL', findings)
        self.assertEqual(findings['RELEASE_ORDER_NOT_TERMINAL']['evidence_refs'], ['E-003', 'E-004'])
        self.assertEqual(findings['LATE_FILL_AFTER_RELEASE']['evidence_refs'], ['E-004', 'E-005'])
        self.assertEqual(len(self.memo['events']), 5)

    def test_later_current_pass_does_not_remove_critical_history(self):
        source = sample_traces()['Pending cancel → early release → late fill']
        source['events'].extend([
            {'event_id': 'E-006', 'observed_utc': '2026-10-27T14:30:06Z',
             'type': 'POSITION_OBSERVED', 'position_qty': 4},
            {'event_id': 'E-007', 'observed_utc': '2026-10-27T14:30:07Z',
             'type': 'PROTECTION_OBSERVED', 'status': 'ACTIVE', 'coverage_qty': 4},
        ])
        memo = build_memo(audit_trace(parse_trace(json.dumps(source))))
        self.assertEqual(memo['checks']['G03']['current_status'], 'PASS')
        self.assertTrue(memo['checks']['G03']['critical_history'])

    def test_individual_missing_data_stays_unknown(self):
        source = sample_traces()['Broker query unavailable']
        source['quote'] = None
        memo = build_memo(audit_trace(parse_trace(json.dumps(source))))
        self.assertEqual(memo['checks']['G01']['status'], 'UNKNOWN')
        self.assertEqual(memo['checks']['G02']['status'], 'UNKNOWN')
        self.assertEqual(memo['checks']['G03']['current_status'], 'BLOCK')
        self.assertEqual(memo['checks']['G04']['gross_status'], 'UNKNOWN')
        self.assertEqual(memo['checks']['G04']['heat_status'], 'UNKNOWN')

    def test_gross_and_heat_are_not_collapsed_into_one_status(self):
        source = sample_traces()['Exposure and heat exceed caps']
        source['exposure']['positions'][0]['risk_to_stop'] = None
        memo = build_memo(audit_trace(parse_trace(json.dumps(source))))
        self.assertEqual(memo['checks']['G04']['gross_status'], 'VETO')
        self.assertEqual(memo['checks']['G04']['heat_status'], 'UNKNOWN')

    def test_memo_rejects_changed_claims_or_omitted_history(self):
        for edit in ('status', 'history', 'event'):
            with self.subTest(edit=edit):
                altered = copy.deepcopy(self.memo)
                if edit == 'status':
                    altered['checks']['G03']['current_status'] = 'PASS'
                elif edit == 'history':
                    altered['checks']['G03']['critical_history'] = []
                else:
                    altered['events'][3]['observed_utc'] = '2026-10-27T14:30:08Z'
                with self.assertRaises(ReviewError):
                    validate_memo(self.report, altered)

    def test_validation_distinguishes_numeric_one_from_boolean_true(self):
        source = sample_traces()['Cancel confirmed with zero fill']
        source['quote']['age_seconds'] = 1
        report = audit_trace(parse_trace(json.dumps(source)))
        altered = build_memo(report)
        altered['checks']['G01']['age_seconds'] = True
        with self.assertRaises(ReviewError):
            validate_memo(report, altered)

    def test_rejects_forged_audit_report(self):
        with self.assertRaises(ReviewError):
            build_memo(replace(self.report, current_gate='PASS'))

    def test_review_requires_both_acknowledgements(self):
        for evidence, scope in ((False, True), (True, False), (False, False)):
            with self.subTest(evidence=evidence, scope=scope):
                with self.assertRaises(ReviewError):
                    self.record(evidence=evidence, scope=scope)
        with self.assertRaises(ReviewError):
            self.record(evidence=1, scope=True)

    def test_flagging_does_not_require_acknowledgements(self):
        review = self.record('NEEDS_MANUAL_REVIEW', evidence=False, scope=False)
        self.assertEqual(review.decision, 'NEEDS_MANUAL_REVIEW')
        self.assertFalse(review.evidence_acknowledged)

    def test_review_does_not_clear_critical_findings_or_approve_trade(self):
        review = self.record()
        output = review_download(self.report, self.memo, review)
        self.assertIn('RELEASE_ORDER_NOT_TERMINAL', output)
        self.assertIn('LATE_FILL_AFTER_RELEASE', output)
        self.assertIn('does not verify identity', output)
        self.assertIn('AI-generated text', output)
        self.assertIn('no broker action or trade authorization', output.lower())
        self.assertNotIn('## Unverified model explanation', output)

    def test_reviewer_record_cannot_move_to_different_case(self):
        review = self.record()
        other = audited('Cancel confirmed with zero fill')
        with self.assertRaises(ReviewError):
            review_download(other, build_memo(other), review)

    def test_reviewer_record_rejects_tampered_or_invalid_state(self):
        review = self.record()
        for tampered in (replace(review, memo_sha256='0' * 64),
                         replace(review, evidence_acknowledged=False),
                         replace(review, recorded_utc='not a time'),
                         replace(review, decision='TRADE_APPROVED')):
            with self.subTest(tampered=tampered):
                with self.assertRaises(ReviewError):
                    review_download(self.report, self.memo, tampered)

    def test_review_rejects_stale_memo(self):
        other = audited('Cancel confirmed with zero fill')
        with self.assertRaises(ReviewError):
            record_review(other, self.memo, 'REVIEWED', evidence_acknowledged=True,
                          scope_acknowledged=True, now=self.time)

    def test_no_invalid_decision_or_naive_time(self):
        with self.assertRaises(ReviewError):
            self.record('TRADE_APPROVED')
        with self.assertRaises(ReviewError):
            record_review(self.report, self.memo, 'REVIEWED', evidence_acknowledged=True,
                          scope_acknowledged=True, now=datetime(2026, 10, 27, 16))


if __name__ == '__main__':
    unittest.main()
