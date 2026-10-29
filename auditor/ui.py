"""Shared modern UI components, themes, and visual renderers for Streamlit pages."""
from __future__ import annotations

import html
from typing import Any


CUSTOM_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }
  code, pre, [class*="stCode"] {
    font-family: 'JetBrains Mono', monospace !important;
  }
  .block-container {
    max-width: 1440px;
    padding-top: 1.8rem;
    padding-bottom: 3.5rem;
  }
  h1, h2, h3 {
    letter-spacing: -0.03em;
    font-weight: 700;
  }
  h1 { font-size: 2.3rem !important; }
  h2 { font-size: 1.5rem !important; margin-top: 1.2rem; }
  h3 { font-size: 1.2rem !important; }

  [data-testid="stSidebar"] {
    background-color: #0d151e !important;
    border-right: 1px solid #1c2c38;
  }
  [data-testid="stMetric"] {
    background: #111d28;
    border: 1px solid #223444;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }
  [data-testid="stMetricLabel"] {
    color: #8da4b5 !important;
    font-size: 0.8rem !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 1.45rem !important;
  }

  .kicker {
    color: #4ade80;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 0.35rem;
  }
  .subhead {
    color: #94a3b8;
    font-size: 0.98rem;
    line-height: 1.55;
    max-width: 860px;
  }
  .rule {
    border-top: 1px solid #1e293b;
    margin: 1.2rem 0;
  }
  .tag {
    display: inline-block;
    border: 1px solid #166534;
    background: #052e16;
    color: #86efac;
    border-radius: 9999px;
    padding: 0.2rem 0.65rem;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.05em;
  }

  /* Timeline styling */
  .timeline-container {
    display: flex;
    align-items: stretch;
    gap: 10px;
    overflow-x: auto;
    padding: 12px 4px 18px 4px;
    margin: 10px 0 16px 0;
  }
  .timeline-node {
    flex: 1 0 190px;
    max-width: 240px;
    background: #111d28;
    border: 1px solid #233546;
    border-radius: 10px;
    padding: 12px 14px;
    position: relative;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.25);
    transition: transform 0.15s ease, border-color 0.15s ease;
  }
  .timeline-node:hover {
    transform: translateY(-2px);
    border-color: #38bdf8;
  }
  .timeline-node.critical {
    background: linear-gradient(180deg, #2a1215 0%, #1a0f12 100%) !important;
    border: 2px solid #ef4444 !important;
    box-shadow: 0 0 18px rgba(239, 68, 68, 0.28) !important;
  }
  .timeline-node.warning {
    background: linear-gradient(180deg, #271e0c 0%, #17130a 100%) !important;
    border: 1.5px solid #f59e0b !important;
    box-shadow: 0 0 14px rgba(245, 158, 11, 0.22) !important;
  }
  .timeline-arrow {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #475569;
    font-size: 1.25rem;
    font-weight: 700;
    user-select: none;
    padding: 0 2px;
  }
  .node-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .node-id {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    font-weight: 700;
    color: #94a3b8;
  }
  .node-kind {
    font-size: 0.65rem;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    background: #1e293b;
    color: #cbd5e1;
    text-transform: uppercase;
  }
  .node-time {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: #64748b;
    margin-bottom: 8px;
  }
  .node-status {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 0.88rem;
    color: #f1f5f9;
    margin-bottom: 4px;
  }
  .node-details {
    font-size: 0.72rem;
    color: #94a3b8;
    line-height: 1.4;
  }
  .node-alert {
    margin-top: 8px;
    padding: 4px 6px;
    border-radius: 4px;
    background: rgba(239, 68, 68, 0.22);
    border: 1px solid #ef4444;
    color: #fca5a5;
    font-size: 0.7rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  /* Claims Table */
  .claims-table-wrapper {
    overflow-x: auto;
    margin: 12px 0;
    border-radius: 10px;
    border: 1px solid #223444;
  }
  .claims-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    text-align: left;
    background: #0d151e;
  }
  .claims-table th {
    background: #152230;
    color: #94a3b8;
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 10px 14px;
    border-bottom: 1px solid #223444;
  }
  .claims-table td {
    padding: 10px 14px;
    border-bottom: 1px solid #1a2734;
    color: #e2e8f0;
  }
  .claims-table tr:hover {
    background: #111d28;
  }
  .badge-match {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #064e3b;
    color: #6ee7b7;
    border: 1px solid #059669;
    padding: 3px 10px;
    border-radius: 9999px;
    font-weight: 700;
    font-size: 0.74rem;
    letter-spacing: 0.03em;
  }
  .badge-contradiction {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #450a0a;
    color: #fca5a5;
    border: 1px solid #dc2626;
    padding: 3px 10px;
    border-radius: 9999px;
    font-weight: 700;
    font-size: 0.74rem;
    letter-spacing: 0.03em;
  }
  .badge-unverified {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #451a03;
    color: #fde047;
    border: 1px solid #d97706;
    padding: 3px 10px;
    border-radius: 9999px;
    font-weight: 700;
    font-size: 0.74rem;
    letter-spacing: 0.03em;
  }

  /* Status Cards */
  .gate-card {
    background: #111d28;
    border: 1px solid #223444;
    border-radius: 10px;
    padding: 14px 16px;
    height: 100%;
  }
  .gate-card.pass {
    border-left: 4px solid #10b981;
  }
  .gate-card.block {
    border-left: 4px solid #ef4444;
  }
  .gate-card.critical {
    border-left: 4px solid #dc2626;
    background: linear-gradient(180deg, #1f1013 0%, #111d28 100%);
  }
  .gate-card.unknown {
    border-left: 4px solid #64748b;
  }
</style>
"""


def _compact_html(markup: str) -> str:
    """Join lines without indentation or blank lines.

    Streamlit renders st.markdown through CommonMark: a blank line ends a raw HTML
    block, and a following line indented four or more spaces becomes a literal
    code block. Compacting keeps each component one HTML block.
    """
    return "".join(line.strip() for line in markup.splitlines())


def apply_theme() -> None:
    """Inject unified custom styling into the active Streamlit session."""
    try:
        import streamlit as st
        if hasattr(st, "markdown"):
            st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    except (ImportError, AttributeError):
        pass


def render_lifecycle_timeline_html(report: Any) -> str:
    """Generate a high-impact horizontal visual timeline from a LifecycleReport."""
    if not hasattr(report, "events") or not report.events:
        return ""

    # Map critical findings to affected event IDs
    critical_events: dict[str, str] = {}
    if hasattr(report, "findings"):
        for f in report.findings:
            if getattr(f, "severity", "") == "CRITICAL":
                code = getattr(f, "code", "CRITICAL_ANOMALY")
                for ref in getattr(f, "evidence_refs", ()):
                    critical_events[ref] = code
                if getattr(f, "event_id", ""):
                    critical_events[f.event_id] = code

    items_html = []
    events_list = list(report.events)
    for idx, event in enumerate(events_list):
        raw_eid = str(getattr(event, "event_id", f"E-{idx:03d}"))
        eid = html.escape(raw_eid)
        observed = html.escape(str(getattr(event, "observed_utc", "")).split("T")[-1].replace("Z", ""))
        kind = html.escape(str(getattr(event, "kind", "EVENT")))
        status = html.escape(str(getattr(event, "status", "—") or "—"))

        # Details line
        details = []
        fill = getattr(event, "cumulative_fill", None)
        if fill is not None:
            details.append(f"Fill: {fill}")
        pos = getattr(event, "position_qty", None)
        if pos is not None:
            details.append(f"Pos: {pos}")
        cov = getattr(event, "coverage_qty", None)
        if cov is not None:
            details.append(f"Cov: {cov}")
        details_str = html.escape(" · ".join(details) if details else "None")

        is_critical = raw_eid in critical_events
        node_class = "timeline-node critical" if is_critical else "timeline-node"

        alert_badge = ""
        if is_critical:
            reason = critical_events[raw_eid].replace("_", " ")
            alert_badge = f'<div class="node-alert">⚠️ {html.escape(reason)}</div>'

        node_html = f"""
        <div class="{node_class}">
          <div class="node-header">
            <span class="node-id">{eid}</span>
            <span class="node-kind">{kind}</span>
          </div>
          <div class="node-time">⏱ {observed} UTC</div>
          <div class="node-status">{status}</div>
          <div class="node-details">{details_str}</div>
          {alert_badge}
        </div>
        """
        items_html.append(node_html)

        # Arrow connector between nodes
        if idx < len(events_list) - 1:
            items_html.append('<div class="timeline-arrow">→</div>')

    return _compact_html(f'<div class="timeline-container">{"".join(items_html)}</div>')


def render_claims_table_html(checked_claims: Any) -> str:
    """Render structured model claim verifications with high-contrast colorized badges."""
    claims = getattr(checked_claims, "claims", ())
    if not claims:
        return ""

    rows_html = []
    for c in claims:
        idx = html.escape(str(getattr(c, "index", 1)))
        scope = getattr(c, "scope", "")
        eid = getattr(c, "event_id", "")
        field = getattr(c, "field", "")
        ref = html.escape(f"{eid or scope}.{field}")
        claimed = html.escape(str(getattr(c, "claimed", "")))
        record = getattr(c, "evidence", None)
        record_str = "unknown / n.a." if record is None else str(record)
        record_str = html.escape(record_str)
        status = getattr(c, "status", "UNVERIFIED")
        reason = html.escape(str(getattr(c, "reason", "")))

        if status == "EVIDENCE_MATCH":
            badge = '<span class="badge-match">● EVIDENCE_MATCH</span>'
        elif status == "CONTRADICTION":
            badge = '<span class="badge-contradiction">✕ CONTRADICTION</span>'
        else:
            badge = '<span class="badge-unverified">▲ UNVERIFIED</span>'

        row = f"""
        <tr>
          <td style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#94a3b8;">#{idx}</td>
          <td style="font-family:'JetBrains Mono', monospace; color:#38bdf8;">{ref}</td>
          <td><code style="color:#f1f5f9;">{claimed}</code></td>
          <td><code style="color:#94a3b8;">{record_str}</code></td>
          <td>{badge}</td>
          <td style="font-family:'JetBrains Mono', monospace; font-size:0.75rem; color:#64748b;">{reason}</td>
        </tr>
        """
        rows_html.append(row)

    return _compact_html(f"""
    <div class="claims-table-wrapper">
      <table class="claims-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Field Reference</th>
            <th>Model Claim</th>
            <th>Synthetic Record</th>
            <th>Verification</th>
            <th>Reason Code</th>
          </tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
    </div>
    """)
