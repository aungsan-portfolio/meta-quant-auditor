import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from auditor.paper_observer import (EVENT_END, EVENT_START, ObservationError, capture_source,
                                    normalize_record, poll_status, read_snapshot, synthetic_events)
from tools import observe_paper_gates


def source_record(**overrides):
    value = {'timestamp': '2026-10-27T14:30:00.123456Z', 'symbol': 'NVDA',
             'strategy': 'GAP_AND_GO', 'stage': 'STAGE_QUOTE_HEALTH',
             'decision': 'REJECT', 'reason_code': 'EXCESSIVE_SPREAD',
             'account_id': 'private-account-sentinel', 'order_id': 'private-order-sentinel',
             'human_message': 'private-message-sentinel',
             'metadata': {'secret': 'private-secret-sentinel'}, 'raw_conf': 0.82}
    value.update(overrides)
    return value


class LocalPaperObservationTests(unittest.TestCase):
    def test_drops_private_fields_and_normalizes_selected_gate_event(self):
        event = normalize_record(source_record())
        self.assertEqual(event, {'observed_utc': '2026-10-27T14:30:00.123456Z',
                                 'symbol': 'NVDA', 'strategy': 'GAP_AND_GO',
                                 'stage': 'QUOTE_HEALTH', 'decision': 'REJECT',
                                 'reason': 'EXCESSIVE_SPREAD'})
        self.assertNotIn('sentinel', json.dumps(event))
        self.assertNotIn('0.82', json.dumps(event))

    def test_unrecognized_text_is_replaced_not_displayed(self):
        event = normalize_record(source_record(strategy='PRIVATE_LONG_TEXT', stage='private-stage-sentinel',
                                                decision='private-decision-sentinel',
                                                reason_code='private-reason-sentinel'))
        self.assertTrue(all(event[x] == 'OTHER_OR_UNKNOWN' for x in ('strategy', 'stage', 'decision', 'reason')))
        self.assertNotIn('sentinel', json.dumps(event))
        self.assertIsNone(normalize_record(source_record(symbol='PRIVATE-SYMBOL-SENTINEL')))

    def test_observed_allowlisted_reasons_are_preserved_without_raw_data(self):
        recognized = (
            'CONFIDENCE_BELOW_FLOOR', 'ENTRY_CUTOFF_TIME', 'SPY_BEARISH_5M',
            'COUNTER_TREND_SHORT_VETO', 'PRIOR_EXIT_PENDING_RECONCILIATION',
            'RSI_OVERBOUGHT', 'RSI_OVERSOLD', 'TECH_CLUSTER_CAP',
        )
        for reason in recognized:
            with self.subTest(reason=reason):
                value = normalize_record(source_record(reason_code=reason))
                self.assertEqual(value['reason'], reason)
                self.assertNotIn('sentinel', json.dumps(value))
        other = normalize_record(source_record(reason_code='CONFIDENCE_BELOW_FLOOR_PRIVATE_SENTINEL'))
        self.assertEqual(other['reason'], 'OTHER_OR_UNKNOWN')
        self.assertNotIn('SENTINEL', json.dumps(other))

    def test_known_confidence_stage_is_normalized_but_other_raw_stages_are_hidden(self):
        value = normalize_record(source_record(stage='STAGE_CONFIDENCE', reason_code='CONFIDENCE_BELOW_FLOOR'))
        self.assertEqual((value['stage'], value['reason']), ('CONFIDENCE', 'CONFIDENCE_BELOW_FLOOR'))
        other = normalize_record(source_record(stage='PRIVATE_STAGE_SENTINEL'))
        self.assertEqual(other['stage'], 'OTHER_OR_UNKNOWN')
        self.assertNotIn('SENTINEL', json.dumps(other))

    def test_reason_descriptions_do_not_assert_that_inputs_were_verified(self):
        from auditor.paper_observer import REASONS, REASON_DESCRIPTIONS
        self.assertTrue(REASONS.issubset(REASON_DESCRIPTIONS))
        self.assertIn('Reported', REASON_DESCRIPTIONS['CONFIDENCE_BELOW_FLOOR'])
        self.assertIn('withheld', REASON_DESCRIPTIONS['OTHER_OR_UNKNOWN'])

    def test_accepts_event_window_only_and_requires_aware_timestamp(self):
        for stamp in (EVENT_START.isoformat(), EVENT_END.isoformat()):
            self.assertIsNotNone(normalize_record(source_record(timestamp=stamp)))
        for stamp in ((EVENT_START - timedelta(microseconds=1)).isoformat(),
                      (EVENT_END + timedelta(microseconds=1)).isoformat(),
                      '2026-10-27T14:30:00'):
            self.assertIsNone(normalize_record(source_record(timestamp=stamp)))

    def test_source_read_is_bounded_ignores_invalid_and_partial_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'gate.jsonl'
            raw = (json.dumps(source_record()) + '\n'
                   + '{"symbol":"NVDA","symbol":"TSLA"}\n'
                   + json.dumps(source_record(symbol='AAPL'))[:-2]).encode()
            source.write_bytes(raw)
            before = source.read_bytes()
            snap = capture_source(source, checked=EVENT_END)
            self.assertTrue(snap['readable'])
            self.assertEqual(len(snap['events']), 1)
            self.assertEqual(snap['ignored_records'], 1)
            self.assertEqual(source.read_bytes(), before)
            self.assertNotIn('sentinel', json.dumps(snap))

    def test_missing_or_wrong_file_type_is_not_marked_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'wrong.txt'
            source.write_text(json.dumps(source_record()) + '\n', encoding='utf8')
            self.assertFalse(capture_source(source, checked=EVENT_END)['readable'])
            self.assertFalse(capture_source(Path(folder) / 'missing.jsonl', checked=EVENT_END)['readable'])

    def test_event_list_limit_is_labeled_as_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'gate.jsonl'
            source.write_text((json.dumps(source_record()) + '\n') * 201, encoding='utf8')
            snap = capture_source(source, checked=EVENT_END)
            self.assertTrue(snap['events_truncated'])
            self.assertEqual(len(snap['events']), 200)

    def test_snapshot_rejects_extra_fields_and_unreadable_source_with_events(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'gate.jsonl', Path(folder) / 'snapshot.json'
            source.write_text(json.dumps(source_record()) + '\n', encoding='utf8')
            snap = capture_source(source, checked=EVENT_END)
            output.write_text(json.dumps(snap), encoding='utf8')
            self.assertEqual(read_snapshot(output)['events'][0]['symbol'], 'NVDA')
            snap['events'][0]['account_id'] = 'private-account-sentinel'
            output.write_text(json.dumps(snap), encoding='utf8')
            with self.assertRaises(ObservationError):
                read_snapshot(output)
            snap['events'][0].pop('account_id')
            snap['readable'] = False
            output.write_text(json.dumps(snap), encoding='utf8')
            with self.assertRaises(ObservationError):
                read_snapshot(output)

    def test_recent_poll_is_not_conflated_with_broker_or_market_freshness(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'gate.jsonl'
            source.write_text(json.dumps(source_record()) + '\n', encoding='utf8')
            now = datetime(2026, 10, 28, tzinfo=timezone.utc)
            snap = capture_source(source, checked=now)
            self.assertEqual(poll_status(snap, now=now + timedelta(seconds=5)), 'POLL_RECENT')
            self.assertEqual(poll_status(snap, now=now + timedelta(seconds=16)), 'POLL_STALE')
            self.assertEqual(poll_status(snap, now=now - timedelta(seconds=11)), 'CLOCK_MISMATCH')
            snap['readable'] = False
            self.assertEqual(poll_status(snap, now=now), 'SOURCE_UNAVAILABLE')

    def test_cli_requires_paper_ack_and_writes_only_allowlisted_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.jsonl'
            raw = json.dumps(source_record()) + '\n'
            source.write_text(raw, encoding='utf8')
            with patch.object(observe_paper_gates, 'ROOT', root), \
                 patch('sys.argv', ['observer', '--source', str(source), '--confirm-paper-source']), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(observe_paper_gates.main(), 0)
            snapshot = (root / 'data' / 'paper_gate_observations.json').read_text(encoding='utf8')
            self.assertNotIn('sentinel', snapshot)
            self.assertEqual(source.read_text(encoding='utf8'), raw)
            with patch.object(observe_paper_gates, 'ROOT', root), \
                 patch('sys.argv', ['observer', '--source', str(source)]), \
                 patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit):
                    observe_paper_gates.main()

    def test_replay_is_explicitly_sample_data_with_valid_fields(self):
        events = synthetic_events()
        self.assertTrue(events)
        self.assertTrue(any(e['decision'] == 'REJECT' for e in events))
        self.assertTrue(all('observed_utc' in e for e in events))


if __name__ == '__main__':
    unittest.main()
