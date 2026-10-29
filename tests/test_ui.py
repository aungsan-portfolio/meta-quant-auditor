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


if __name__ == "__main__":
    unittest.main()
