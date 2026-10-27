"""Streamlit view of the synthetic order-cancellation audit."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.cancellation import LifecycleError, audit_trace, markdown_report, model_evidence, parse_trace, sample_traces
from auditor.cancellation_model import LifecycleSelection, explain_lifecycle
from auditor.jobs import ExplanationJob


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Cancellation Safety Audit', page_icon='🔎', layout='wide')
st.title('Cancellation safety audit')
st.caption('Review a fictional cancellation timeline and separately inspect synthetic portfolio limits.')
st.info('Synthetic cases only. This read-only demo does not connect to a broker, release reservations, or place orders.')

examples = sample_traces()
with st.sidebar:
    st.subheader('Case source')
    source = st.radio('Choose input', ['Built-in lifecycle case', 'Upload synthetic lifecycle JSON'])
    if source == 'Built-in lifecycle case':
        scenario = st.selectbox('Example', list(examples))
        raw = json.dumps(examples[scenario], indent=2)
        st.download_button('Download example lifecycle JSON', raw,
                           file_name='synthetic-lifecycle.json', mime='application/json')
    else:
        st.caption('Upload only fictional cases in this project’s format. Never upload real account, order, market, credential, or private data.')
        uploaded = st.file_uploader('Synthetic lifecycle JSON', type=['json'])
        raw = uploaded.getvalue() if uploaded is not None else None
        if raw is None:
            st.caption('A built-in example can be downloaded as a template.')

if raw is None:
    st.stop()
try:
    report = audit_trace(parse_trace(raw))
except LifecycleError as exc:
    st.error(f'Case rejected: {exc}')
    st.stop()

if 'cancellation_job' not in st.session_state:
    st.session_state.cancellation_job = ExplanationJob(worker=explain_lifecycle)
job = st.session_state.cancellation_job
selection = LifecycleSelection()

critical = [f for f in report.findings if f.severity == 'CRITICAL']
if critical:
    st.error('Recorded unsafe release or late-fill sequence detected in this synthetic trace.')
elif report.current_gate == 'BLOCK':
    st.warning(f'G03: BLOCK — {report.current_reason}')
else:
    st.success(f'G03: PASS for this simulated cancellation check — {report.current_reason}')
st.caption(f'Trace {report.trace_id} · A single gate PASS never authorizes a trade.')

st.subheader('G01 / G02 · Synthetic quote checks')
if report.quote is None:
    st.info('No quote example was supplied. No quote gate PASS is inferred.')
else:
    q = report.quote
    first_quote, second_quote = st.columns(2)
    age = 'unknown' if q.age_seconds is None else f'{q.age_seconds:.3f} s'
    spread = 'unknown' if q.spread_pct is None else f'{q.spread_pct:.3f}%'
    first_quote.metric('G01 · Quote age', age)
    age_limit = 'unknown' if q.age_limit_seconds is None else f'{q.age_limit_seconds} s'
    first_quote.caption(f'Limit: {age_limit} · {q.freshness_status} · {q.freshness_reason}')
    second_quote.metric('G02 · Spread', spread)
    spread_cap = 'unknown' if q.spread_cap_pct is None else f'{q.spread_cap_pct}%'
    second_quote.caption(f'Cap: {spread_cap} · {q.spread_status} · {q.spread_reason}')
    st.caption(f'Fictional bid: {report.source_trace.quote.bid} · ask: {report.source_trace.quote.ask} · session: {q.session}')

left, right = st.columns([1.3, 1], gap='large')
with left:
    st.subheader('1 · Lifecycle evidence')
    st.dataframe([
        {'Observed UTC': event.observed_utc, 'Broker event UTC': event.broker_event_utc or 'unknown / n/a',
         'Event': event.event_id, 'Type': event.kind,
         'Status': event.status if event.status is not None else '—',
         'Fill': str(event.cumulative_fill) if event.cumulative_fill is not None else 'unknown / n/a',
         'Position': str(event.position_qty) if event.position_qty is not None else 'unknown / n/a',
         'Coverage': str(event.coverage_qty) if event.coverage_qty is not None else 'unknown / n/a'}
        for event in report.events
    ], hide_index=True, use_container_width=True)
    st.subheader('G03 · Deterministic findings')
    if report.findings:
        st.dataframe([{'Event': f.event_id, 'Severity': f.severity, 'Finding': f.code,
                       'Evidence': ', '.join(f.evidence_refs)} for f in report.findings],
                     hide_index=True, use_container_width=True)
    else:
        st.caption('No release or anomaly was recorded in this case.')
    st.caption('All timestamps and protection observations are synthetic claims. Broker and local clock alignment is assumed, not verified.')
    st.download_button('Download deterministic audit report', markdown_report(report),
                       file_name='synthetic-cancellation-audit.md', mime='text/markdown')

with right:
    st.subheader('G04 · Synthetic exposure checks')
    if report.exposure is None:
        st.info('No exposure example was supplied. No exposure PASS is inferred.')
    else:
        exposure = report.exposure
        gross = 'unknown' if exposure.gross_pct is None else f'{exposure.gross_pct:.3f}%'
        heat = 'unknown' if exposure.heat_pct is None else f'{exposure.heat_pct:.3f}%'
        st.metric('Gross exposure / equity', gross, help='Sum of absolute supplied market values divided by supplied equity.')
        gross_cap = 'unknown' if exposure.gross_cap_pct is None else f'{exposure.gross_cap_pct}%'
        st.caption(f'Cap: {gross_cap} · {exposure.gross_status}')
        st.metric('Supplied stop-risk heat / equity', heat, help='Sum of supplied risk-to-stop amounts divided by supplied equity.')
        heat_cap = 'unknown' if exposure.heat_cap_pct is None else f'{exposure.heat_cap_pct}%'
        st.caption(f'Cap: {heat_cap} · {exposure.heat_status}')
        st.caption('These caps and numbers are fictional. Stop-risk values are inputs, not verified losses or production bot policy.')
    st.divider()
    st.subheader('2 · Explain with Muse Spark')
    st.caption('Only the validated synthetic evidence shown below is sent after an explicit request. The raw uploaded file is not sent.')
    with st.expander('Review evidence before sending'):
        st.json(model_evidence(report))
    status, result = job.state(report, selection)
    api_key = os.environ.get('BASETEN_API_KEY', '').strip()
    usable = bool(api_key) and api_key != 'your_baseten_api_key_here'
    if not usable:
        st.info('Set a local BASETEN_API_KEY to request an explanation. Offline audit still works.')
    busy = status in ('PENDING', 'OTHER_PENDING')
    if st.button('Explain cancellation audit', type='primary', disabled=busy or not usable, use_container_width=True):
        if job.start(report, selection, api_key):
            st.rerun()
    if busy:
        st.info('The model is working. Deterministic checks remain visible.')
        st.button('Refresh cancellation explanation', use_container_width=True)
    elif status == 'DONE' and result is not None:
        if result.status == 'AVAILABLE':
            st.success('Explanation received · compare its claims with the evidence')
            st.text(result.text)
            st.download_button('Download audit with unverified model text', markdown_report(report, result.text),
                               file_name='synthetic-cancellation-with-explanation.md', mime='text/markdown')
        else:
            st.warning(f'Model explanation unavailable: {result.reason}')
    else:
        st.info('Explicit model requests may consume credits. There are no automatic retries.')
