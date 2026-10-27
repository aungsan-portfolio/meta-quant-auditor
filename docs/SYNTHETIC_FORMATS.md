# Synthetic input formats and limits

The formats below were written during the event for this standalone project. They are not compatible with the participant's pre-event bot trace schema. Obtain a valid starting example using the **Download example JSON** buttons in the app. Files are bounded to 65,536 bytes; the synthetic case accepts 1–12 attempts and the lifecycle format accepts 1–40 events. Duplicate JSON keys, non-finite values, extra fields and invalid types are rejected.

## Synthetic case

`mqa.synthetic-case.v1` describes a fictional shared quote, fictional account-state flags, illustrative policies, and chronologically ordered hypothetical attempts. IDs use numeric synthetic identifiers (`SIM-001`, `A-001`, `C-001`); arbitrary text and broker IDs are not supported. Attempts contain a UTC timestamp ending in `Z` and a hypothetical planned entry.

The workbench recomputes five gates:

- **Quote freshness:** age versus the configured regular or extended session limit; an unknown session blocks.
- **Spread quality:** `(ask - bid) / midpoint * 100` versus the example percent limit.
- **Account state:** unknown positions or a latched entry state block.
- **Chase guard:** the positive percent difference between ask and a hypothetical planned entry versus the example limit.
- **Duplicate simulation:** an in-memory key is reserved for each eligible simulated candidate; a later eligible repeat of that key blocks.

Spread and chase percentages are rounded to six decimal places before comparison. Thresholds, prices, account flags and all results are fictional and do not represent production bot policy. The same quote and account-state snapshot applies to every attempt in a case. An eligible result applies only to the replay, not a trade. Duplicate keys do not persist across runs and provide no brokerage protection.

## Synthetic event trace

`mqa.synthetic-report.v1` contains normalized gate records, timestamps, a trace UUID, fictional simulation keys and claimed simulated decisions. It can be exported from a replay or from the trace inspector's examples. The inspector checks known outcome/reason combinations against the supplied evidence and the recorded gate set. It marks contradictory records `REVIEW_REQUIRED` and missing gates or uncertain prior ledger context `INCOMPLETE`. A `CONSISTENT` result means only that the supplied records agree with one another under these toy rules; it cannot establish authenticity, correct production policy, execution safety, or that an event really happened.

## Synthetic cancellation lifecycle

`mqa.synthetic-lifecycle.v1` accepts 1–40 fictional observations in strictly increasing UTC seconds. Supported event types are `BROKER_ORDER`, `BROKER_FILL`, `CANCEL_REQUESTED`, `QUERY_FAILED`, `RESERVATION_RELEASED`, `POSITION_OBSERVED` and `PROTECTION_OBSERVED`. `BROKER_FILL` includes a separate synthetic broker-reported event time. A later observation alone is not treated as proof that the fill occurred after release. A late-fill finding based on reported timestamps assumes local and broker clocks are aligned; neither timestamps nor event authenticity are independently verified. IDs have the restricted numeric form `E-001`. Download examples from **Cancellation Safety**; unknown fields and duplicate keys are rejected. A user-supplied `synthetic` flag is not proof that data is safe or actually synthetic.

The optional quote object adds G01 session-aware freshness and G02 spread checks to the same report. Unknown sessions block freshness; missing ages, prices or limits remain `UNKNOWN`. A crossed or nonpositive quote blocks spread validation. Valid synthetic spread is computed from bid/ask midpoint and rounded to six decimals before comparison. These quote thresholds are demo inputs, not the participant's bot settings.

G03 records a critical finding if a simulated reservation release occurs while the last broker status is non-terminal or unknown, or after a positive fill without a subsequent position observation. For a nonzero position it also requires a later ACTIVE coverage observation with the same quantity. Cancel requested is not cancellation confirmed. A later fill and any prior early release remain visible even if later evidence appears safe. Conflicting status or decreasing cumulative fill blocks the check. Reservation releases and coverage observations are synthetic assertions, not proof that a reservation existed or that a valid linked protective order existed. No side, stop type, order linkage, actual broker state, persistent reservation or live risk policy is verified.

G04 optionally evaluates two independent supplied measures. Gross percentage is `sum(abs(market_value)) / equity * 100`; stop-risk heat is `sum(risk_to_stop) / equity * 100`. These per-position inputs and both caps are fictional, not calculated from an actual broker or the user's production thresholds. Each percentage is rounded to six decimals before comparison. Zero or missing equity, a missing input, or a missing cap yields `UNKNOWN` for the affected measure, without concealing a separate breach in the other. Positive equity smaller than 0.01 is rejected as outside this demo's supported numeric range. A pass for either G03 or G04 does not authorize an order or imply an overall risk decision.

## Human review of a synthetic memo

The cancellation page reconstructs a structured memo from the current deterministic report, including all events and historical critical findings. It compares the entire structured memo with a fresh reconstruction and assigns a SHA-256 content fingerprint. A reviewer can mark it reviewed after affirming the evidence and scope, or flag it for manual review without those affirmations. Changing evidence or a computed finding changes the fingerprint, so an earlier action is not shown for the changed memo.

The record lives in the Streamlit browser session unless the user downloads it. The fingerprint and on-device timestamp provide neither authenticated identity nor a digital signature; a checkbox cannot establish that evidence was actually read. This review does not clear a safety finding, authorize trading, or check natural-language model claims. Optional AI prose is deliberately excluded from the structured memo and reviewed export and still needs independent human comparison with the evidence. The fixed Plan → Act → Observe display describes application steps, not an autonomous model-agent execution trace.

## Privacy and model boundary

Do not upload real bot logs, account information, orders, credentials, personally identifiable information or proprietary data. Setting `synthetic: true` does not sanitize a real file. Validators restrict fields and identifier shapes, but no validation can guarantee that a user has not placed sensitive information in an allowed value. When requested, only the normalized fields shown in the app and deterministic checks go to Baseten; the original file does not. Generated text is unverified and can contain errors.
