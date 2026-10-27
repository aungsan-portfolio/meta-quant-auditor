"""Local Streamlit demo for fictional quote-gate audit events."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.audit import SCENARIOS, evaluate, model_evidence
from auditor.jobs import ExplanationJob


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Meta Quant Auditor', page_icon='🔎', layout='wide')

st.markdown('''
<style>
  .block-container { max-width: 1420px; padding-top: 2.2rem; padding-bottom: 4rem; }
  h1, h2, h3 { letter-spacing: -0.035em; }
  h1 { font-size: 2.7rem !important; }
  [data-testid="stSidebar"] { border-right: 1px solid #1c2c38; }
  [data-testid="stMetric"] { background: #111d28; border: 1px solid #253645; border-radius: 12px; padding: 1rem; }
  [data-testid="stMetricLabel"] { color: #9db2bf; }
  .kicker { color: #6bd5ca; font-size: .73rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; }
  .subhead { color: #a4b5c3; font-size: 1rem; line-height: 1.6; max-width: 860px; }
  .rule { border-top: 1px solid #24323d; margin: 1.4rem 0; }
  .tag { display: inline-block; border: 1px solid #2b5d5b; background: #102d2c; color: #9ce7da; border-radius: 100px; padding: .25rem .65rem; font-size: .75rem; font-weight: 650; }
</style>
''', unsafe_allow_html=True)

if 'explanation_job' not in st.session_state:
    st.session_state.explanation_job = ExplanationJob()
job = st.session_state.explanation_job

with st.sidebar:
    st.markdown('<div class="kicker">◈ Meta Quant Auditor</div>', unsafe_allow_html=True)
    st.markdown('### Audit workspace')
    st.caption('Explore fictional quote checks with an optional Meta model explanation.')
    selected = st.radio('Synthetic scenario', SCENARIOS, format_func=lambda item: item.title)
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    st.markdown('**Demo boundaries**')
    st.caption('No broker connection · No order placement · No real market data')
    st.caption('Gate outcomes are deterministic. The model does not change them.')

trace = evaluate(selected)
st.markdown('<span class="tag">● SYNTHETIC · LOCAL DEMO</span>', unsafe_allow_html=True)
st.markdown('# See why the gate stopped.')
st.markdown('<p class="subhead">Inspect an audit event, compare its evidence with the configured limit, and ask Muse Spark to explain the result.</p>', unsafe_allow_html=True)
st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric('Scenario', selected.title)
col_b.metric('Quote spread', f'{trace.spread_pct:.3f}%')
col_c.metric('Quote age', f'{selected.quote_age_seconds:.1f} s')
col_d.metric('Session', selected.session.replace('_', ' '))
st.caption('All prices, times, limits, and events shown here are fabricated for this demo.')

left, right = st.columns([1.15, 1], gap='large')
with left:
    st.markdown('<div class="kicker">01 / Deterministic checks</div>', unsafe_allow_html=True)
    st.subheader('Inspect the evidence')
    st.write(selected.description)
    for gate in trace.findings:
        label = f'{gate.event_id}  ·  {gate.gate}  ·  {gate.outcome}'
        with st.container(border=True):
            st.markdown(f'**{label}**')
            if gate.limit is None:
                st.caption('Session policy is unknown; freshness is blocked.')
            else:
                st.caption(f'Observed {gate.observed:.3f} {gate.unit}  /  limit {gate.limit:.3f} {gate.unit}')
                st.progress(min(max(gate.observed / gate.limit, 0.0), 1.0))
            st.code(gate.reason, language=None)

    finding = st.radio(
        'Choose an event to explain', trace.findings,
        format_func=lambda item: f'{item.event_id} · {item.gate} · {item.outcome}',
        key='selected_gate',
    )
    with st.expander('View the synthetic evidence sent to the model'):
        st.json(model_evidence(trace, finding))
    st.download_button(
        'Download selected evidence',
        json.dumps(model_evidence(trace, finding), indent=2),
        file_name=f'{selected.slug}-{finding.event_id}.json', mime='application/json',
    )

with right:
    st.markdown('<div class="kicker">02 / Meta explanation</div>', unsafe_allow_html=True)
    st.subheader('Understand the result')
    st.caption('Muse Spark Open on Baseten · Explicit request · No automatic retries')
    status, result = job.state(trace, finding)
    api_key = os.environ.get('BASETEN_API_KEY', '').strip()
    if not api_key or api_key == 'your_baseten_api_key_here':
        st.info('Set BASETEN_API_KEY in a local .env file to request an explanation. The audit checks work without a key.')
    busy = status in ('PENDING', 'OTHER_PENDING')
    if st.button('Explain selected event', type='primary', disabled=busy or not api_key or api_key == 'your_baseten_api_key_here', use_container_width=True):
        if job.start(trace, finding, api_key):
            st.rerun()
    if busy:
        st.info('The model request is running. The deterministic gate results remain available above.')
        st.button('Refresh explanation status', use_container_width=True)
    elif status == 'DONE' and result is not None:
        if result.status == 'AVAILABLE':
            st.success('Explanation received · review it against the evidence')
            st.text(result.text)
        else:
            st.warning(f'Model explanation unavailable: {result.reason}')
            st.caption('The gate results remain unchanged. You can try again manually.')
    else:
        st.info('Select a gate, then request an explanation. A real request may consume API credits.')

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    st.markdown('**Read this as an audit, not a trade signal.**')
    st.caption('A PASS applies to one gate only. AI text can be incorrect; it never authorizes a trade or changes the audit result.')
    st.caption(f'Trace {trace.trace_id} · {trace.schema_version} · synthetic UTC {trace.observed_utc}')
