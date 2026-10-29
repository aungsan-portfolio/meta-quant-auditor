"""Streamlit page for synthetic multi-gate decision replay."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.jobs import ExplanationJob
from auditor.workbench import CaseError, markdown_report, parse_case, replay_case, report_evidence, sample_cases
from auditor.workbench_model import WholeReplay, explain_replay
from auditor.ui import apply_theme


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Decision Audit Workbench', page_icon='🔎', layout='wide')
apply_theme()
st.title('Decision audit workbench')
st.caption('Replay a synthetic paper-simulation case, inspect each gate, then export the evidence.')
st.info('Synthetic input only. No broker, real market data, trading signal, or order execution is supported.')

examples = sample_cases()
with st.sidebar:
    st.subheader('Case source')
    source = st.radio('Choose input', ['Built-in case', 'Upload synthetic JSON'])
    if source == 'Built-in case':
        scenario_name = st.selectbox('Example', list(examples))
        source_text = json.dumps(examples[scenario_name], indent=2)
        st.download_button('Download example JSON', source_text,
                           file_name='synthetic-case.json', mime='application/json')
    else:
        st.caption('Use only the documented fictional case format. Do not upload real account, order, market, or credential data.')
        upload = st.file_uploader('Synthetic case JSON', type=['json'])
        source_text = upload.getvalue() if upload is not None else None
        if source_text is None:
            st.caption('Download an example from the built-in case selector as a template.')

if source_text is None:
    st.stop()
try:
    case = parse_case(source_text)
    replay = replay_case(case)
except CaseError as exc:
    st.error(f'Case rejected: {exc}')
    st.stop()

if 'workbench_job' not in st.session_state:
    st.session_state.workbench_job = ExplanationJob(worker=explain_replay)
job = st.session_state.workbench_job
selection = WholeReplay()

count_blocked = sum(item.decision != 'ELIGIBLE' for item in replay.attempts)
first, second, third = st.columns(3)
first.metric('Simulated attempts', len(replay.attempts))
second.metric('Blocked or vetoed', count_blocked)
third.metric('Case', replay.case_id)
st.caption(f'Trace {replay.trace_id} · Stable simulation keys are in-memory only; this is not broker idempotency.')

left, right = st.columns([1.3, 1], gap='large')
with left:
    st.subheader('1 · Replay and gate evidence')
    for item in replay.attempts:
        with st.container(border=True):
            st.markdown(f'**{item.attempt_id} · {item.decision}**')
            st.caption(f'{item.timestamp_utc} · simulation key {item.simulation_key}')
            st.dataframe([
                {'Event': gate.event_id, 'Gate': gate.gate, 'Outcome': gate.outcome,
                 'Reason': gate.reason_code, 'Observed': str(gate.observed) if gate.observed is not None else 'unknown',
                 'Limit': str(gate.limit) if gate.limit is not None else 'unknown', 'Unit': gate.unit}
                for gate in item.gates
            ], hide_index=True, width="stretch")
    st.caption('ELIGIBLE means the fictional checks passed in this replay only. It never authorizes a trade.')
    st.download_button('Download deterministic Markdown report', markdown_report(replay),
                       file_name='synthetic-audit-report.md', mime='text/markdown')
    st.download_button('Download synthetic event trace JSON', json.dumps(report_evidence(replay), indent=2),
                       file_name='synthetic-event-trace.json', mime='application/json')

with right:
    st.subheader('2 · Explain the replay with Muse Spark')
    st.caption('The model receives only the displayed, allowlisted synthetic facts after you explicitly request it. No raw uploaded file is sent.')
    with st.expander('Review model evidence before sending'):
        st.json(report_evidence(replay))
    status, result = job.state(replay, selection)
    api_key = os.environ.get('BASETEN_API_KEY', '').strip()
    usable_key = bool(api_key) and api_key != 'your_baseten_api_key_here'
    if not usable_key:
        st.info('Set a local BASETEN_API_KEY to request an explanation. Offline replay still works.')
    busy = status in ('PENDING', 'OTHER_PENDING')
    if st.button('Explain full replay', type='primary', disabled=busy or not usable_key, width="stretch"):
        if job.start(replay, selection, api_key):
            st.rerun()
    if busy:
        st.info('The model is working. The replay evidence remains available.')
        st.button('Refresh replay explanation', width="stretch")
    elif status == 'DONE' and result is not None:
        if result.status == 'AVAILABLE':
            st.success('Explanation received · verify every claim against the evidence')
            st.text(result.text)
            st.download_button('Download report with unverified model text',
                               markdown_report(replay, result.text),
                               file_name='synthetic-audit-with-explanation.md', mime='text/markdown')
        else:
            st.warning(f'Model explanation unavailable: {result.reason}')
    else:
        st.info('Explicit model requests may consume API credits. There are no automatic retries.')
