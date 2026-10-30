"""Unit tests for auditor.ui visual components."""
import json
import unittest

from auditor.cancellation import audit_trace, parse_trace, sample_traces
from auditor.claims import example_claims, verify_claims
from auditor.ui import CUSTOM_CSS, apply_theme, render_claims_table_html, render_lifecycle_timeline_html


class UITests(unittest.TestCase):
    def setUp(self):
        sample = sample_traces()["Pending cancel → early release → late fill"]
        self.report = audit_trace(parse_trace(json.dumps(sample)))

    def test_custom_css_structure(self):
        self.assertIn(".timeline-container", CUSTOM_CSS)
        self.assertIn(".claims-table", CUSTOM_CSS)
        self.assertIn(".badge-match", CUSTOM_CSS)
        self.assertIn(".badge-contradiction", CUSTOM_CSS)
        self.assertIn(".badge-unverified", CUSTOM_CSS)

    def test_render_lifecycle_timeline_highlights_critical_events(self):
        html_out = render_lifecycle_timeline_html(self.report)
        self.assertIn('class="timeline-container"', html_out)
        self.assertIn("E-001", html_out)
        self.assertIn("E-004", html_out)
        self.assertIn("E-005", html_out)
        self.assertIn("timeline-node critical", html_out)
        self.assertIn("timeline-arrow", html_out)
        self.assertIn("RELEASE ORDER NOT TERMINAL", html_out)
        self.assertIn("LATE FILL AFTER RELEASE", html_out)

    def test_render_lifecycle_timeline_empty(self):
        self.assertEqual(render_lifecycle_timeline_html(None), "")
        self.assertEqual(render_lifecycle_timeline_html(object()), "")

    def test_render_claims_table_colorized_badges(self):
        text = example_claims(self.report)
        checked = verify_claims(self.report, text)
        html_out = render_claims_table_html(checked)
        self.assertIn('class="claims-table"', html_out)
        self.assertIn("badge-match", html_out)
        self.assertIn("badge-contradiction", html_out)
        self.assertIn("badge-unverified", html_out)
        self.assertIn("● EVIDENCE_MATCH", html_out)
        self.assertIn("✕ CONTRADICTION", html_out)
        self.assertIn("▲ UNVERIFIED", html_out)

    def test_render_claims_table_empty(self):
        self.assertEqual(render_claims_table_html(None), "")
        self.assertEqual(render_claims_table_html(object()), "")

    def test_apply_theme_graceful(self):
        # Should execute safely in any python environment
        apply_theme()

    def test_components_are_single_line_html_for_markdown(self):
        # st.markdown uses CommonMark: a blank line ends a raw HTML block and a
        # following line indented by four spaces is shown as literal code.
        checked = verify_claims(self.report, example_claims(self.report))
        for html_out in (render_lifecycle_timeline_html(self.report), render_claims_table_html(checked)):
            with self.subTest(component=html_out[:30]):
                self.assertTrue(html_out.startswith('<div class="'))
                self.assertNotIn("\n", html_out)

    def test_record_column_is_not_labeled_ground_truth(self):
        checked = verify_claims(self.report, example_claims(self.report))
        html_out = render_claims_table_html(checked)
        self.assertIn("<th>Synthetic Record</th>", html_out)
        self.assertNotIn("Ground Truth", html_out)

    def test_untrusted_values_are_escaped(self):
        from types import SimpleNamespace
        payload = '<img src=x onerror=alert(1)>'
        event = SimpleNamespace(event_id=payload, observed_utc=payload, kind=payload, status=payload,
                                cumulative_fill=None, position_qty=None, coverage_qty=None)
        finding = SimpleNamespace(severity="CRITICAL", code=payload, evidence_refs=(payload,), event_id=payload)
        timeline = render_lifecycle_timeline_html(SimpleNamespace(events=(event,), findings=(finding,)))
        claim = SimpleNamespace(index=1, scope=payload, event_id=payload, field=payload, claimed=payload,
                                evidence=payload, status="CONTRADICTION", reason=payload)
        table = render_claims_table_html(SimpleNamespace(claims=(claim,)))
        for html_out in (timeline, table):
            with self.subTest(component=html_out[:30]):
                self.assertNotIn("<img", html_out)
                self.assertIn("&lt;img", html_out)
        self.assertIn("timeline-node critical", timeline)

    def test_timeline_distinguishes_critical_from_context_events(self):
        html_out = render_lifecycle_timeline_html(self.report)
        # E-003 is context only -> warning class
        self.assertIn('node-id">E-003</span>', html_out)
        self.assertIn('timeline-node warning', html_out)
        # E-004 is primary critical for RELEASE_ORDER_NOT_TERMINAL
        # E-005 is primary critical for LATE_FILL_AFTER_RELEASE
        self.assertIn('RELEASE ORDER NOT TERMINAL', html_out)
        self.assertIn('LATE FILL AFTER RELEASE', html_out)


if __name__ == "__main__":
    unittest.main()
