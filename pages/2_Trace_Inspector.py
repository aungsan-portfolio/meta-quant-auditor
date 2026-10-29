"""Inspect recorded synthetic event traces without altering their gate results."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.jobs import ExplanationJob
from auditor.ui import apply_theme
from auditor.trace_review import review_evidence, review_markdown, review_trace
from auditor.workbench import CaseError, parse_case, replay_case, report_evidence, sample_cases
from auditor.workbench_model import WholeReplay, explain_recorded_review


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Recorded Trace Inspector', page_icon='🔎', layout='wide')
apply_theme()
st.title('Recorded trace inspector')
st.caption('Check whether recorded synthetic gate outcomes and decisions agree with their evidence.')
st.info('Only this project’s synthetic trace format is accepted. This does not prove an event occurred and does not connect to a trading bot.')

with st.sidebar:
    st.subheader('Trace source')
    source = st.radio('Choose trace', ['Built-in trace', 'Upload synthetic trace JSON'])
    if source == 'Built-in trace':
        example = st.selectbox('Example', ['Consistent duplicate', 'Inconsistent spread record'])
        source_case = sample_cases()['Duplicate attempt' if example == 'Consistent duplicate' else 'Wide spread']
        trace = report_evidence(replay_case(parse_case(json.dumps(source_case))))
        if example == 'Inconsistent spread record':
            trace['attempts'][0]['gates'][1]['outcome'] = 'PASS'
            trace['attempts'][0]['gates'][1]['reason_code'] = 'WITHIN_SPREAD_LIMIT'
        trace_text = json.dumps(trace, indent=2)
        st.download_button('Download example trace JSON', trace_text,
                           file_name='synthetic-recorded-trace.json', mime='application/json')
    else:
        st.caption('Use only newly generated fictional traces. Do not upload real account, order, market, or credential data.')
        upload = st.file_uploader('Synthetic event trace JSON', type=['json'])
        trace_text = upload.getvalue() if upload is not None else None
        if trace_text is None:
            st.caption('Download a trace from the Audit Workbench or from a built-in example.')

if trace_text is None:
    st.stop()
try:
    review = review_trace(trace_text)
except CaseError as exc:
    st.error(f'Trace rejected: {exc}')
    st.stop()

if 'trace_review_job' not in st.session_state:
    st.session_state.trace_review_job = ExplanationJob(worker=explain_recorded_review)
job = st.session_state.trace_review_job
selection = WholeReplay()

if review.status == 'CONSISTENT':
    st.success('CONSISTENT: the included synthetic records agree with their supplied evidence.')
elif review.status == 'INCOMPLETE':
    st.warning('INCOMPLETE: required gates or prior ledger context are missing.')
else:
    st.error('REVIEW REQUIRED: at least one recorded result conflicts with its evidence or other records.')
st.caption(f'Trace {review.trace_id} · Consistency is not proof of a historical or real-world event.')

left, right = st.columns([1.3, 1], gap='large')
with left:
    st.subheader('1 · Deterministic consistency checks')
    st.dataframe([{'Event': check.event_id, 'Status': check.status, 'Check': check.code}
                  for check in review.checks], hide_index=True, width="stretch")
    for item in review.replay.attempts:
        with st.expander(f'{item.attempt_id} · recorded decision {item.decision}'):
            st.dataframe([
                {'Event': gate.event_id, 'Gate': gate.gate, 'Outcome': gate.outcome,
                 'Reason': gate.reason_code,
                 'Observed': str(gate.observed) if gate.observed is not None else 'unknown',
                 'Limit': str(gate.limit) if gate.limit is not None else 'unknown', 'Unit': gate.unit}
                for gate in item.gates
            ], hide_index=True, width="stretch")
    st.download_button('Download consistency report', review_markdown(review),
                       file_name='synthetic-trace-review.md', mime='text/markdown')

with right:
    st.subheader('2 · Explain checks with Muse Spark')
    st.caption('Only normalized synthetic evidence and check codes are sent after an explicit request. The uploaded raw file is not sent.')
    with st.expander('Review model evidence before sending'):
        st.json(review_evidence(review))
    status, result = job.state(review, selection)
    api_key = os.environ.get('BASETEN_API_KEY', '').strip()
    usable_key = bool(api_key) and api_key != 'your_baseten_api_key_here'
    if not usable_key:
        st.info('Set a local BASETEN_API_KEY to request an explanation. Offline checks still work.')
    busy = status in ('PENDING', 'OTHER_PENDING')
    if st.button('Explain trace review', type='primary', disabled=busy or not usable_key, width="stretch"):
        if job.start(review, selection, api_key):
            st.rerun()
    if busy:
        st.info('The model is working. Deterministic checks remain visible.')
        st.button('Refresh trace explanation', width="stretch")
    elif status == 'DONE' and result is not None:
        if result.status == 'AVAILABLE':
            st.success('Explanation received · compare every claim with the checks')
            st.text(result.text)
            st.download_button('Download review with unverified model text',
                               review_markdown(review, result.text),
                               file_name='synthetic-review-with-explanation.md', mime='text/markdown')
        else:
            st.warning(f'Model explanation unavailable: {result.reason}')
    else:
        st.info('Explicit model requests may consume API credits. There are no automatic retries.')
