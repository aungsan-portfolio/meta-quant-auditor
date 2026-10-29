"""Streamlit view of the synthetic order-cancellation audit."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from auditor.cancellation import LifecycleError, audit_trace, markdown_report, model_evidence, parse_trace, sample_traces
from auditor.cancellation_model import LifecycleSelection, explain_lifecycle
from auditor.claims import ClaimsError, example_claims, verify_claims
from auditor.claims_model import ClaimsSelection, generate_claims
from auditor.followup import FollowupError, append_followup, evidence_request
from auditor.jobs import ExplanationJob
from auditor.review import ReviewError, build_memo, record_review, review_download, validate_memo
from auditor.ui import apply_theme, render_claims_table_html, render_lifecycle_timeline_html


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)
st.set_page_config(page_title='Cancellation Safety Audit', page_icon='🔎', layout='wide')
apply_theme()
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
    base_report = audit_trace(parse_trace(raw))
    if 'cancellation_followups' not in st.session_state:
        st.session_state.cancellation_followups = {}
    active_raw = st.session_state.cancellation_followups.get(base_report.trace_id, raw)
    report = audit_trace(parse_trace(active_raw))
    missing = evidence_request(report)
    memo = build_memo(report)
    memo_digest = validate_memo(report, memo)
except LifecycleError as exc:
    st.error(f'Case rejected: {exc}')
    st.stop()
except (ReviewError, FollowupError):
    st.error('The synthetic audit could not be reconstructed from the current checks.')
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

st.subheader('Audit checklist')
st.caption('Each check is calculated from the current fictional case. Unknown data is not a pass.')
g01, g02, g03, g04 = st.columns(4)
q_check = memo['checks']['G01']
s_check = memo['checks']['G02']
c_check = memo['checks']['G03']
x_check = memo['checks']['G04']
g01.metric('G01 · Quote freshness', q_check['status'])
g01.caption(q_check['reason'])
g02.metric('G02 · Spread quality', s_check['status'])
g02.caption(s_check['reason'])
history_count = len(c_check['critical_history'])
g03.metric('G03 · Cancellation', 'CRITICAL HISTORY' if history_count else c_check['current_status'])
g03.caption(f"Current gate: {c_check['current_status']} · Critical history: {history_count}")
g04.metric('G04 · Portfolio limits', f"{x_check['gross_status']} / {x_check['heat_status']}")
g04.caption('Gross exposure / supplied stop-risk heat')
st.caption('G03 preserves historical critical findings even if a later current gate passes. G04 measures are separate.')

with st.expander('Audit workflow · Plan → Act → Observe'):
    st.write('**Plan:** Read the selected synthetic case and apply the coded quote, cancellation and portfolio checks.')
    st.write('**Act:** Reconstruct and check the case locally; no broker is contacted.')
    st.write(f"**Observe:** {len(report.events)} fictional events and {len(report.findings)} findings; "
             f"{history_count} critical historical findings.")
    st.caption('These are fixed application steps. They are not an autonomous model plan or a model tool-use log.')

st.subheader('Missing lifecycle evidence')
st.caption('This status concerns G03 lifecycle evidence only; it is not an overall trade decision.')
if missing.status == 'NEEDS_INPUT':
    st.warning(f'NEEDS_INPUT · {missing.reason}')
    st.write(missing.request)
    st.caption('Add a fictional follow-up below. The app does not connect to a broker. '
               'The example timestamp advances by one simulated second.')
    with st.form(f'fictional_followup_{report.trace_id}'):
        if missing.event_type == 'BROKER_ORDER':
            next_status = st.selectbox('Fictional broker status',
                                       ['CANCELED', 'EXPIRED', 'REJECTED', 'FILLED', 'PENDING_CANCEL', 'UNKNOWN'])
            next_fill = st.number_input('Fictional cumulative fill', min_value=0.0, value=0.0, step=1.0)
            fill_unknown = st.checkbox('Cumulative fill is unknown')
            next_fields = {'status': next_status, 'cumulative_fill': None if fill_unknown else next_fill}
        elif missing.event_type == 'POSITION_OBSERVED':
            next_position = st.number_input('Fictional observed position quantity', min_value=0.0, value=0.0, step=1.0)
            position_unknown = st.checkbox('Position quantity is unknown')
            next_fields = {'position_qty': None if position_unknown else next_position}
        else:
            next_status = st.selectbox('Fictional protection status', ['ACTIVE', 'PENDING_CANCEL', 'MISSING', 'UNKNOWN'])
            next_coverage = st.number_input('Fictional protection coverage quantity', min_value=0.0, value=0.0, step=1.0)
            coverage_unknown = st.checkbox('Coverage quantity is unknown')
            next_fields = {'status': next_status, 'coverage_qty': None if coverage_unknown else next_coverage}
        add_followup = st.form_submit_button('Add fictional follow-up and recheck', width="stretch")
    if add_followup:
        try:
            st.session_state.cancellation_followups[base_report.trace_id] = append_followup(report, next_fields)
            st.rerun()
        except FollowupError as exc:
            st.warning(str(exc))
elif missing.status == 'REVIEW_REQUIRED':
    st.warning(f'REVIEW_REQUIRED · {missing.reason}')
    st.write(missing.request)
else:
    st.info(f'READY_FOR_REVIEW · {missing.reason}')
    st.write(missing.request)
if base_report.trace_id in st.session_state.cancellation_followups:
    st.caption('Follow-up observations are session-only and do not alter the original example. '
               'Historical findings remain in the audit.')
    st.download_button('Download fictional follow-up trace', active_raw,
                       file_name='synthetic-followup.json', mime='application/json')
    if st.button('Reset fictional follow-ups'):
        st.session_state.cancellation_followups.pop(base_report.trace_id, None)
        st.rerun()

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
    st.markdown(render_lifecycle_timeline_html(report), unsafe_allow_html=True)
    with st.expander('View tabular event records', expanded=False):
        st.dataframe([
            {'Observed UTC': event.observed_utc, 'Broker event UTC': event.broker_event_utc or 'unknown / n/a',
             'Event': event.event_id, 'Type': event.kind,
             'Status': event.status if event.status is not None else '—',
             'Fill': str(event.cumulative_fill) if event.cumulative_fill is not None else 'unknown / n/a',
             'Position': str(event.position_qty) if event.position_qty is not None else 'unknown / n/a',
             'Coverage': str(event.coverage_qty) if event.coverage_qty is not None else 'unknown / n/a'}
            for event in report.events
        ], hide_index=True, width="stretch")
    st.subheader('G03 · Deterministic findings')
    if report.findings:
        st.dataframe([{'Event': f.event_id, 'Severity': f.severity, 'Finding': f.code,
                       'Evidence': ', '.join(f.evidence_refs)} for f in report.findings],
                     hide_index=True, width="stretch")
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
    if st.button('Explain cancellation audit', type='primary', disabled=busy or not usable, width="stretch"):
        if job.start(report, selection, api_key):
            st.rerun()
    if busy:
        st.info('The model is working. Deterministic checks remain visible.')
        st.button('Refresh cancellation explanation', width="stretch")
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

st.divider()
st.subheader('2b · Check structured claims against evidence')
st.caption('Only listed scalar claims are checked against this fictional record. '
           'Narrative interpretations, missing facts and real-world truth are not verified.')
if 'cancellation_claims_job' not in st.session_state:
    st.session_state.cancellation_claims_job = ExplanationJob(worker=generate_claims)
if 'cancellation_claims_mode' not in st.session_state:
    st.session_state.cancellation_claims_mode = {}
claims_job = st.session_state.cancellation_claims_job
claims_selection = ClaimsSelection()
claims_status, claims_result = claims_job.state(report, claims_selection)
claims_busy = claims_status in ('PENDING', 'OTHER_PENDING')
sample_button, model_button = st.columns(2)
if sample_button.button('Try fictional claims · no model', width="stretch"):
    st.session_state.cancellation_claims_mode[report.trace_id] = 'SAMPLE'
if model_button.button('Ask Muse Spark for structured claims', disabled=claims_busy or not usable,
                       width="stretch"):
    if claims_job.start(report, claims_selection, api_key):
        st.session_state.cancellation_claims_mode[report.trace_id] = 'MODEL'
        st.rerun()

mode = st.session_state.cancellation_claims_mode.get(report.trace_id)
claims_text = None
if mode == 'SAMPLE':
    st.info('Fictional sample claims; no AI model was called.')
    claims_text = example_claims(report)
elif mode == 'MODEL':
    if claims_busy:
        st.info('The model is working; the offline audit remains available.')
        st.button('Refresh structured claims')
    elif claims_status == 'DONE' and claims_result is not None:
        if claims_result.status == 'AVAILABLE':
            st.caption('Structured response received from Muse Spark. The following field checks run locally.')
            claims_text = claims_result.text
        else:
            st.warning(f'Claims unavailable: {claims_result.reason}. No claim has been verified.')
    else:
        st.info('No model result for this synthetic case.')
else:
    st.caption('Try the offline sample, or request a model response. Model calls may consume credits.')

if claims_text is not None:
    try:
        checked = verify_claims(report, claims_text)
    except ClaimsError as exc:
        st.warning(f'Claims unavailable: {exc} No claim has been verified.')
    else:
        st.markdown(render_claims_table_html(checked), unsafe_allow_html=True)
        with st.expander('View raw claims dataframe', expanded=False):
            st.dataframe([{'Claim': c.index, 'Reference': f'{c.event_id or c.scope}.{c.field}',
                           'Claimed': str(c.claimed),
                           'Record': 'unknown / n.a.' if c.evidence is None else str(c.evidence),
                           'Result': c.status, 'Reason': c.reason} for c in checked.claims],
                         hide_index=True, width="stretch")
        st.caption('EVIDENCE_MATCH means an exact match to a supplied synthetic field, not proof of an actual event.')
        if checked.interpretation:
            st.warning('The following interpretation is unverified and is not part of the field checks.')
            st.text(checked.interpretation)

with st.expander('🛡️ Audit scope & synthetic verification boundaries', expanded=False):
    st.caption('All timestamps and protection observations are synthetic claims. Broker and local clock alignment is assumed, not verified.')
    st.caption('G03 preserves historical critical findings even if a later current gate passes. G04 measures are separate.')
    st.caption('A single gate PASS never authorizes a trade or order placement.')
    st.caption('Only listed scalar claims are checked against this fictional record. Narrative interpretations and real-world truth are not verified.')

st.divider()
st.subheader('3 · Human review of the deterministic memo')
st.caption('Review the checklist and lifecycle evidence above. This records a reviewer action for the fictional case, not a trade decision.')
st.info('The memo was reconstructed from the coded checks. Optional model prose is not included or automatically verified.')
with st.expander('Inspect the structured memo'):
    st.json(memo)
st.caption(f'Memo fingerprint: {memo_digest} · This identifies content; it is not a digital signature.')
if 'cancellation_reviews' not in st.session_state:
    st.session_state.cancellation_reviews = {}

with st.form(f'cancellation_review_{memo_digest}'):
    evidence_ack = st.checkbox('I compared the checklist, recorded findings, and event evidence for this case.')
    scope_ack = st.checkbox('I understand this is fictional, AI prose is unverified, and this review does not authorize a trade.')
    review_button, flag_button = st.columns(2)
    reviewed = review_button.form_submit_button('Mark audit memo reviewed', width="stretch")
    flagged = flag_button.form_submit_button('Flag for manual review', width="stretch")

if reviewed or flagged:
    try:
        review = record_review(report, memo, 'REVIEWED' if reviewed else 'NEEDS_MANUAL_REVIEW',
                               evidence_acknowledged=evidence_ack, scope_acknowledged=scope_ack)
        st.session_state.cancellation_reviews[memo_digest] = review
    except ReviewError as exc:
        st.warning(str(exc))

review = st.session_state.cancellation_reviews.get(memo_digest)
if review is not None:
    try:
        download = review_download(report, memo, review)
    except ReviewError:
        st.error('This review no longer matches the current synthetic evidence.')
    else:
        if review.decision == 'REVIEWED':
            st.success('Memo marked reviewed. This action does not clear any finding or verify model prose.')
        else:
            st.warning('Memo flagged for manual review.')
        st.caption(f'Recorded at {review.recorded_utc} using this device clock. '
                   'No reviewer identity is verified; the action remains in this browser session unless downloaded.')
        st.download_button('Download reviewed synthetic audit', download,
                           file_name='synthetic-audit-review.md', mime='text/markdown')
else:
    st.caption('No reviewer action recorded for this memo. Switching to different evidence requires a new review.')
