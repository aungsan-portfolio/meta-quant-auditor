"""Opt-in bounded agent over scripted FICTIONAL lifecycle evidence."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.agent import AgentRun, SCENARIOS
from auditor.agent_jobs import AgentJob
from auditor.agent_model import SYSTEM
from auditor.ui import apply_theme


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Synthetic Auditor Agent', page_icon='🔎', layout='wide')
apply_theme()
st.title('Synthetic Auditor Agent')
st.info('Experimental draft · scripted FICTIONAL snapshots only. No broker or trade execution.')
if 'auditor_agent_job' not in st.session_state:
    st.session_state.auditor_agent_job = AgentJob()
job = st.session_state.auditor_agent_job
busy, snapshot = job.snapshot()
scenario_id = st.selectbox('Built-in agent scenario', list(SCENARIOS),
                           format_func=SCENARIOS.get, disabled=busy)
if st.button('Start agent', disabled=busy):
    st.session_state.auditor_agent_preview = scenario_id
preview_id = st.session_state.get('auditor_agent_preview')
if preview_id == scenario_id:
    st.subheader('Preview before consent')
    st.json(AgentRun(scenario_id).context())
    st.caption('Queries may append only the predefined fictional snapshots from this scenario. '
               'Each subsequent request includes updated synthetic evidence and local tool outputs. '
               'Up to 8 requests; each request worker has a 30-second deadline; no automatic retries.')
    with st.expander('Preview all scripted fictional query snapshots'):
        st.json(AgentRun(scenario_id).scripted_snapshots())
    with st.expander('Fixed model instruction', expanded=True):
        st.text(SYSTEM)
    consent = st.checkbox('I reviewed the synthetic evidence and instruction and agree to send this run to Baseten.',
                          key=f'auditor_agent_consent_{scenario_id}')
    key = os.environ.get('BASETEN_API_KEY', '').strip()
    usable = bool(key) and key != 'your_baseten_api_key_here'
    if not usable:
        st.caption('Configure BASETEN_API_KEY locally to run. Opening this page or preview makes no request.')
    if st.button('Run consented agent', disabled=busy or not consent or not usable):
        if job.start(scenario_id, key, consent=consent):
            st.rerun()
if busy and st.button('Stop after current request'):
    job.stop()
st.button('Refresh agent controls')


@st.fragment(run_every=0.5)
def show_agent_trace():
    running, current = job.snapshot()
    if current is None:
        return
    st.subheader('Live Plan / Act / Observe')
    st.write(f"Scenario: {current['scenario_id']} · Status: {current['status']} · Reason: {current['reason']}")
    st.caption('Run is active; one request at a time.' if running else 'Run ended; no further requests.')
    for step in current['steps']:
        with st.expander(f"Step {step['step']} · {step['action']} · {step['validation']}", expanded=True):
            st.write('Plan · model proposal (reason is unverified)')
            st.json({'action': step['action'], 'args': step['args'], 'reason': step['reason_unverified']})
            st.write(f"Act · local validation: {step['validation']}")
            st.write('Observe · local tool result')
            st.json(step['tool_output'])
    with st.expander('Deterministic current memo and retained history'):
        st.json(current['local_memo'])
    if current['final_report']:
        report = current['final_report']
        st.subheader('Final report · local evidence and claim comparisons')
        st.dataframe(report['claims'], hide_index=True, width='stretch')
        st.warning('Model narrative is unverified. A field match is not proof of real-world truth.')
        st.text(report['narrative_unverified'])
        st.download_button('Download synthetic agent report', json.dumps(report, indent=2),
                           'synthetic-agent-report.json', 'application/json')


show_agent_trace()
