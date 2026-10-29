"""Local, read-only view of replay examples or separately sanitized gate observations."""
from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.jobs import ExplanationJob
from auditor.paper_event_model import (PAPER_SOURCE, SYNTHETIC_SOURCE, SYSTEM, PaperEvidenceError,
                                       PaperSelection, build_evidence, explain_paper_event,
                                       verify_paper_response)
from auditor.paper_observer import (ObservationError, REASON_DESCRIPTIONS, poll_status,
                                    read_snapshot, synthetic_events)


ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / 'data' / 'paper_gate_observations.json'
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Paper Event Cockpit', page_icon='📊', layout='wide')
st.title('Paper event cockpit')
st.caption('Observe a gate timeline. This page cannot place, cancel, or modify orders.')
mode = st.radio('Data source', ['Fictional replay', 'Local sanitized paper events'], horizontal=True)


def show_events(events: list[dict], *, replay: bool) -> None:
    if not events:
        st.info('No supported gate observations are available.')
        return
    blocked = sum(e['decision'] in ('REJECT', 'BLOCK', 'VETO') for e in events)
    last = events[-1]
    a, b, c = st.columns(3)
    a.metric('Displayed observations', len(events))
    b.metric('Reject / block records', blocked)
    c.metric('Last recorded symbol', last['symbol'])
    st.caption('Counts are records, not unique trades. A reported fill or submission is not broker verification.')
    st.dataframe([{'Time UTC': e['observed_utc'], 'Symbol': e['symbol'], 'Strategy': e['strategy'],
                   'Gate / stage': e['stage'], 'Reported decision': e['decision'], 'Reason': e['reason']}
                  for e in events], hide_index=True, width="stretch")
    reasons = Counter(e['reason'] for e in events if e['decision'] in ('REJECT', 'BLOCK', 'VETO'))
    if reasons:
        st.subheader('Reported reasons in this sample')
        st.caption('Descriptions interpret source labels only. Inputs, thresholds and broker actions are not independently verified.')
        st.dataframe([{'Reason': reason, 'Records': count,
                       'Meaning': REASON_DESCRIPTIONS.get(reason, 'Unknown label withheld.')}
                      for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))],
                     hide_index=True, width="stretch")
        st.caption('These count records, not unique trades or losses avoided. The last 200 selected records are only a partial sample.')
    if replay:
        st.caption('All records are fictional examples, not evidence of a real bot action.')
    else:
        st.caption('Reported by the operator-selected pre-existing bot; paper mode and provenance are not independently verified.')
    st.info('This gate feed does not supply live prices, verified broker orders, stop coverage, or account balances.')


def show_model_explanation(events: list[dict], *, source_kind: str, source_ready: bool) -> None:
    """Preview and explain one normalized record after explicit user approval."""
    if not events:
        return
    st.divider()
    st.subheader('Explain one reported gate with Muse Spark')
    st.caption('The model cannot change gate results or place orders. Source labels and paper mode are not broker-verified.')
    try:
        evidence_by_id = {build_evidence(event, source_kind).trace_id: event for event in events}
    except PaperEvidenceError:
        st.warning('The selected source contains an invalid normalized record; no model request is available.')
        return
    ids = list(evidence_by_id)
    selection_key = 'paper_selected_evidence_id'
    if st.session_state.get(selection_key) not in evidence_by_id:
        st.session_state[selection_key] = ids[-1]

    def label(identity: str) -> str:
        event = evidence_by_id[identity]
        return f"{event['observed_utc']} · {event['symbol']} · {event['decision']} · {event['reason']}"

    chosen = st.selectbox('Record to explain (local view)', ids, format_func=label, key=selection_key)
    evidence = build_evidence(evidence_by_id[chosen], source_kind)
    st.caption('Selection time, symbol and strategy stay local. A recent file poll does not prove the event itself is recent.')
    with st.expander('Preview the exact facts sent to Baseten', expanded=True):
        st.json(evidence.sent_facts())
        st.caption('Only these four categorical facts and a fixed instruction are sent. No raw log, ticker, '
                   'strategy, exact timestamp, account ID, order ID, price or quantity is sent.')
    with st.expander('View the fixed model instruction'):
        st.text(SYSTEM)
    st.warning('These labels can still be sensitive. A request sends them to Baseten and may consume credits. '
               'Review them before sending; no request is automatic.')

    if 'paper_event_model_job' not in st.session_state:
        st.session_state.paper_event_model_job = ExplanationJob(worker=explain_paper_event)
    job = st.session_state.paper_event_model_job
    selection = PaperSelection()
    status, result = job.state(evidence, selection)
    busy = status in ('PENDING', 'OTHER_PENDING')
    api_key = os.environ.get('BASETEN_API_KEY', '').strip()
    usable = bool(api_key) and api_key != 'your_baseten_api_key_here'
    if not usable:
        st.info('Set BASETEN_API_KEY locally to request an explanation. The local records remain available without it.')
    if not source_ready:
        st.warning('The observer snapshot is unavailable or stale. Refresh it before sending an event.')
    confirmed = st.checkbox('I reviewed these facts and agree to send this selected record to Baseten.',
                            key=f'paper_event_ack_{evidence.trace_id}')
    if st.button('Ask Muse Spark about this record', type='primary',
                 disabled=busy or not usable or not confirmed or not source_ready,
                 key=f'paper_event_ask_{evidence.trace_id}'):
        if confirmed and usable and source_ready and job.start(evidence, selection, api_key):
            st.rerun()
    if busy:
        st.info('The model request is running. Gate records are unchanged.')
        st.button('Refresh paper explanation status', key='paper_event_refresh')
    elif status == 'DONE' and result is not None:
        if result.status != 'AVAILABLE':
            st.warning(f'Model explanation unavailable: {result.reason}. No claims were verified.')
            return
        try:
            checked = verify_paper_response(evidence, result.text)
        except PaperEvidenceError:
            st.warning('Model response was not valid structured JSON. No claims were verified.')
            return
        st.dataframe([{'Field': claim.field, 'Model claim': claim.claimed,
                       'Reported field': claim.reported, 'Result': claim.status}
                      for claim in checked.claims], hide_index=True, width="stretch")
        st.caption('EVIDENCE_MATCH means an exact label match to this local record, not broker confirmation, '
                   'correctness of the policy, or verification of the whole explanation.')
        if checked.has_contradiction:
            st.error('A claim contradicts the selected record. The interpretation is withheld for review.')
        elif any(claim.status == 'UNVERIFIED' for claim in checked.claims):
            st.warning('A source label is unknown. The interpretation is withheld until that evidence is available.')
        else:
            st.warning('The following model interpretation is unverified. It is not a trade signal or authorization.')
            st.text(checked.interpretation)
    else:
        st.caption('Use a fictional replay or explicitly request a model response for a selected local paper record.')


if mode == 'Fictional replay':
    st.info('SYNTHETIC REPLAY · No broker, real market feed, or trading bot is connected.')
    example = synthetic_events()
    step = st.slider('Replay through record', 1, len(example), 1)
    show_events(example[:step], replay=True)
    show_model_explanation(example[:step], source_kind=SYNTHETIC_SOURCE, source_ready=True)
    st.caption('These example rows illustrate the interface; use the cancellation page for the deterministic lifecycle audit.')
    st.page_link('pages/3_Cancellation_Safety.py', label='Open the synthetic cancellation audit')
else:
    st.warning('LOCAL OBSERVATION · Run the app on localhost. Inspect sanitized fields before recording or sharing.')
    st.caption('No broker request is made. A model request occurs only after you review and explicitly approve the limited facts.')

    @st.fragment(run_every=5)
    def show_local_snapshot() -> None:
        try:
            doc = read_snapshot(SNAPSHOT)
        except ObservationError:
            st.warning('Local sanitized snapshot is unavailable. Start the local observer described in the README.')
            return
        state = poll_status(doc, now=datetime.now(timezone.utc))
        if state == 'POLL_RECENT':
            st.info('The local file was checked recently. This does not establish a live bot or fresh market data.')
        else:
            st.warning(f'Local observer status: {state}. Do not treat previous rows as current.')
        st.caption(f"Last observer check: {doc['checked_utc']} · Ignored records: {doc['ignored_records']}")
        if doc['source_tail_only'] or doc['events_truncated']:
            st.warning('Only a bounded tail or the latest 200 matching records are shown; the timeline is incomplete.')
        show_events(doc['events'], replay=False)
        show_model_explanation(doc['events'], source_kind=PAPER_SOURCE, source_ready=state == 'POLL_RECENT')

    show_local_snapshot()
