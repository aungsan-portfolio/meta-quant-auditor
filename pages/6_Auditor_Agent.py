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
ACTION_LABELS = {
    'run_lifecycle_audit': 'Audit the fictional order lifecycle',
    'query_order_status': 'Check the fictional order status',
    'query_position': 'Check the fictional position',
    'query_protection': 'Check the fictional protection',
    'compare_claims': 'Compare claims with the record',
    'request_human_input': 'Ask for human input',
    'finish_report': 'Finish the report',
    'INVALID': 'Invalid model response',
}


def show_observation(output):
    """Explain local output without treating model-generated text as verified."""
    if output.get('error'):
        st.error(f"The run stopped: {output['error']}. See technical details below.")
        return
    source = output.get('source')
    if source == 'LOCAL_DETERMINISTIC_AUDIT':
        gate = output['memo']['checks']['G03']['current_status']
        st.write(f'Local lifecycle audit completed. Current G03 gate: **{gate}**.')
        st.write(output['missing_evidence']['request'])
    elif source == 'SCRIPTED_FICTIONAL_SNAPSHOT':
        if output['availability'] == 'unavailable':
            st.warning('The fictional snapshot is unavailable. The run stopped and needs input.')
        else:
            values = ' · '.join(f"{key.replace('_', ' ')}: {value}"
                                for key, value in output['snapshot'].items())
            st.write('Fictional snapshot received:')
            st.text(values)
            st.write(output['missing_evidence']['request'])
    elif source == 'LOCAL_EVIDENCE_REQUEST':
        st.write(output['request']['request'])
    elif source == 'LOCAL_CLAIM_VERIFIER':
        st.write(f"Local verifier checked {len(output['claims'])} structured claim(s).")
    elif 'narrative_unverified' in output:
        st.write('The local verifier checked the report claims. See the report below.')
    else:
        st.write('See the local result in technical details below.')


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
if st.session_state.get('auditor_agent_selected') != scenario_id:
    st.session_state.auditor_agent_selected = scenario_id
    st.session_state.auditor_agent_preview = None
st.caption('Start agent opens a preview. No model request is sent until you consent and run.')
if st.button('Start agent', disabled=busy):
    st.session_state.auditor_agent_preview = scenario_id
    st.session_state[f'auditor_agent_consent_{scenario_id}'] = False
preview_id = st.session_state.get('auditor_agent_preview')
if preview_id == scenario_id:
    st.subheader('Preview before consent')
    preview = AgentRun(scenario_id)
    context = preview.context()
    evidence = context['evidence']
    st.info('Review this fictional case and the full inputs below. No request has been sent for this preview.')
    summary = st.columns(3)
    summary[0].metric('Fictional events', len(evidence['events']))
    summary[1].metric('Initial gate', evidence['current_gate'])
    summary[2].metric('Evidence status', context['missing_evidence']['status'])
    st.write('Fictional lifecycle:')
    st.dataframe([{'Event': event['event_id'], 'Type': event['kind'],
                   'Status': event['status'] or '—',
                   'Cumulative fill': event['cumulative_fill']}
                  for event in evidence['events']], hide_index=True, width='stretch')
    st.write(context['missing_evidence']['request'])
    st.caption('Queries may append only the predefined fictional snapshots from this scenario. '
               'Each subsequent request includes updated synthetic evidence and local tool outputs. '
               'Up to 8 requests; each request worker has a 30-second deadline; no automatic retries.')
    st.write('Open the sections below to review the complete initial evidence, snapshots, and instruction.')
    with st.expander('Full initial evidence sent to the model', expanded=False):
        st.json(context, expanded=False)
    with st.expander('Preview all scripted fictional query snapshots'):
        st.json(preview.scripted_snapshots(), expanded=False)
    with st.expander('Fixed model instruction', expanded=False):
        st.text(SYSTEM)
    st.caption('After reviewing the preview, tick the box and press Run consented agent.')
    consent = st.checkbox('I reviewed the synthetic evidence and instruction and agree to send this run to Baseten.',
                          key=f'auditor_agent_consent_{scenario_id}')
    key = os.environ.get('BASETEN_API_KEY', '').strip()
    usable = bool(key) and key != 'your_baseten_api_key_here'
    if not usable:
        st.caption('Configure BASETEN_API_KEY locally to run. Opening this page or preview makes no request.')
    if st.button('Run consented agent', disabled=busy or not consent or not usable):
        if job.start(scenario_id, key, consent=consent):
            # A new run must start from a fresh preview and explicit consent.
            st.session_state.auditor_agent_preview = None
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
    if not running and st.session_state.get('auditor_agent_preview') is not None:
        st.caption('The trace below is from the previous run and will be replaced when a new run starts.')
    st.write(f"Scenario: {current['scenario_id']} · Status: {current['status']} · Reason: {current['reason']}")
    st.caption('Run is active; one request at a time.' if running else 'Run ended; no further requests.')
    if running and not current['steps']:
        st.info('Waiting for the first model response. Each request has a 30-second deadline.')
    for step in current['steps']:
        with st.container(border=True):
            label = ACTION_LABELS.get(step['action'], 'Unknown model action')
            st.markdown(f"**Step {step['step']} · {label}**")
            st.write(f"Plan: `{step['action']}` · Act: **{step['validation']}**")
            if step['reason_unverified']:
                st.text(f"Model reason (unverified): {step['reason_unverified']}")
            st.write('Observe:')
            show_observation(step['tool_output'])
            with st.expander('View technical action and result', expanded=False):
                st.json({'action': step['action'], 'args': step['args'],
                         'reason_unverified': step['reason_unverified'],
                         'tool_output': step['tool_output']}, expanded=False)
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
