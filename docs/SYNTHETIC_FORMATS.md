# Synthetic input formats and limits

Both formats below were written during the event for this standalone project. They are not compatible with the participant's pre-event bot trace schema. Obtain a valid starting example using the **Download example JSON** buttons in the app. Files are bounded to 65,536 bytes and 1–12 attempts. Duplicate JSON keys, non-finite values, extra fields and invalid types are rejected.

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

## Privacy and model boundary

Do not upload real bot logs, account information, orders, credentials, personally identifiable information or proprietary data. Setting `synthetic: true` does not sanitize a real file. Validators restrict fields and identifier shapes, but no validation can guarantee that a user has not placed sensitive information in an allowed value. When requested, only the normalized fields shown in the app and deterministic checks go to Baseten; the original file does not. Generated text is unverified and can contain errors.
