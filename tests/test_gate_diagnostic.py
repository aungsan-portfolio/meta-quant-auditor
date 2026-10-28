import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from auditor import paper_observer
from tools import diagnose_paper_gates


def event(**changes):
    value = {'timestamp': '2026-10-28T15:00:00Z', 'symbol': 'NVDA',
             'strategy': 'GAP_AND_GO', 'stage': 'STAGE_QUOTE_HEALTH',
             'decision': 'REJECT', 'reason_code': 'INVALID_GEOMETRY',
             'account_id': 'PRIVATE_ACCOUNT_SENTINEL',
             'metadata': {'api_key': 'PRIVATE_TOKEN_SENTINEL'}}
    value.update(changes)
    return value


class GateDiagnosticTests(unittest.TestCase):
    def test_reasons_are_allowlisted_and_categories_match_observer_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'events.jsonl'
            records = [event()] * 202 + [event(reason_code='PRIVATE_REASON_SENTINEL')]
            invalid = ['{bad-json}', '[]', json.dumps(event(timestamp=None)),
                       json.dumps(event(timestamp='2026-01-01T00:00:00Z')),
                       json.dumps(event(symbol='PRIVATE_SYMBOL_SENTINEL'))]
            p.write_text('\n'.join(json.dumps(r) for r in records) + '\n' + '\n'.join(invalid) + '\n',
                         encoding='utf-8')
            before = p.read_bytes()
            result = diagnose_paper_gates.summarize(p, paper_observer)
            captured = paper_observer.capture_source(p, checked=datetime.now(timezone.utc))
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(result['accepted_in_tail'], 203)
            self.assertEqual(result['ignored_in_tail'], 5)
            self.assertEqual(result['ignored_in_tail'], captured['ignored_records'])
            self.assertEqual(result['last_sample_records'], len(captured['events']))
            self.assertEqual(result['last_sample_reject_records'], 200)
            self.assertEqual(result['last_sample_reject_reasons']['INVALID_GEOMETRY'], 199)
            self.assertEqual(result['last_sample_reject_reasons']['OTHER_OR_UNKNOWN'], 1)
            self.assertNotIn('SENTINEL', json.dumps(result))
            self.assertEqual(set(result['ignored_categories']), {
                'INVALID_JSON_OR_ENCODING', 'NOT_AN_OBJECT', 'INVALID_OR_MISSING_TIMESTAMP',
                'OUTSIDE_EVENT_WINDOW', 'INVALID_OR_MISSING_SYMBOL'})

    def test_pass_records_are_part_of_last_200_before_filtering_rejections(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'events.jsonl'
            records = [event()] * 200 + [event(decision='PASS')]
            p.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')
            result = diagnose_paper_gates.summarize(p, paper_observer)
            self.assertEqual(result['last_sample_records'], 200)
            self.assertEqual(result['last_sample_reject_records'], 199)

    def test_cli_does_not_print_private_content_or_write_source(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'events.jsonl'
            p.write_text(json.dumps(event(reason_code='PRIVATE_REASON_SENTINEL')) + '\n', encoding='utf-8')
            original = p.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                status = diagnose_paper_gates.main(['--project', str(Path.cwd()), '--source', str(p)])
            self.assertEqual(status, 0)
            self.assertNotIn('SENTINEL', output.getvalue())
            self.assertNotIn('NVDA', output.getvalue())
            self.assertIn('OTHER_OR_UNKNOWN: 1', output.getvalue())
            self.assertEqual(p.read_bytes(), original)

    def test_nonterminated_record_is_not_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'events.jsonl'
            p.write_text(json.dumps(event()) + '\n' + json.dumps(event())[:-1], encoding='utf-8')
            result = diagnose_paper_gates.summarize(p, paper_observer)
            self.assertEqual(result['accepted_in_tail'], 1)
            self.assertEqual(result['complete_lines_in_tail'], 1)


if __name__ == '__main__':
    unittest.main()
