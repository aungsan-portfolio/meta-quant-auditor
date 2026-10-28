# Local paper-event observation

The **Paper event cockpit** starts with a fictional step-through replay. It runs without the existing trading bot, credentials, a network request, or a model call. The example events are fabricated; they do not demonstrate real fills or risk intervention.

An optional local adapter can read a gate-decision JSONL ledger from the pre-existing bot. This is a read-only observer of reported gate events, not an execution engine or a broker connection. The operator explicitly declares that the source is paper mode; the program cannot independently establish the account type, event authenticity, or whether an event was actually produced during the hackathon.

## Local setup

Use only a user-controlled, local computer. The checked-in Streamlit server configuration binds to `127.0.0.1`; do not override it to expose a private feed to a network. Do not run the observer on a deployed public application. The input file stays in its original location; the tool only reads it.

In a separate PowerShell window in this project, after replacing the placeholder path with the actual local gate JSONL path:

```powershell
.\.venv\Scripts\python.exe tools\observe_paper_gates.py --source "C:\path\to\trade_gate_decision.jsonl" --confirm-paper-source --follow
```

The tool writes an allowlisted local snapshot to `data/paper_gate_observations.json`, which is ignored by Git. Keep that terminal open for periodic reads. Stop it with Ctrl+C. The **Paper event cockpit** page's *Local sanitized paper events* option checks the snapshot every five seconds. A recent local poll is not proof that the original bot is alive or that market data is fresh.

The input must be a `.jsonl` file. The observer reads at most the last 2,000,000 bytes and shows at most 200 selected records; old records or partial lines can be omitted. Out-of-window, malformed, incomplete or unsupported records can be ignored. It retains only time, a ticker symbol, selected strategy and gate labels, decision and an allowlisted reason. Unknown labels are replaced with `OTHER_OR_UNKNOWN`. It does not export source free text, metadata, account IDs, broker IDs, quantities, prices, P&L, or confidence values. Ticker, strategy, and times can themselves be private: inspect the snapshot before recording or sharing. An allowlist cannot guarantee a file is free of all sensitive information.

The reason allowlist was expanded after the operator shared aggregate diagnostic counts, without providing raw records. The stage mapping also recognizes additional fixed gate labels, including the confidence gate; arbitrary unrecognized labels continue to be withheld. The page summarizes reported reject, block and veto reason labels in the selected sample. A description reflects only the reported label; the observer does not independently validate a quote, score, limit, actual order, or risk action. A reported confidence score is not a validated probability of trading success.

The timestamp filter uses Oct 26, 2026 at noon ET through Nov 4, 2026 at 9 PM ET. A timestamp is only a claim in a local record, and filtering cannot establish provenance or eligibility. Confirm the official event boundaries and organizer's ruling before submission.

This initial observer covers only selected gate records. It does not connect to IEX, obtain current stock prices, verify paper order or fill status, inspect stop coverage, perform risk intervention, or demonstrate the actual bot's complete trading lifecycle. A reported `SUBMISSION_REPORTED` or `FILL_REPORTED` stage is a source assertion, not broker-confirmed proof. The existing audit upload pages remain synthetic-only.

## Optional Meta explanation of a selected record

The cockpit can select one fictional or locally reported record, preview four categorical facts (source kind, stage, decision and reason), and request a Muse Spark explanation only after an explicit per-record checkbox and button click. A fixed system instruction and those four facts are sent to Baseten. No ticker, strategy, timestamp, account or order IDs, price, quantity, or raw record is sent. These labels can still be sensitive; review the preview before authorizing an external request. A model call may consume credits. There are no automatic calls or retries.

The model is asked for three structured label claims and an interpretation. Local code compares each claim with the selected reported field. `EVIDENCE_MATCH` is only a field match; it does not establish source authenticity, correct gate inputs, broker truth, or the interpretation. Unknown source labels are `UNVERIFIED`. A contradiction or unknown label causes the interpretation to be withheld; otherwise the displayed prose is explicitly unverified. An invalid, empty, truncated, or failed response is unavailable and does not change local records. A response is bound to the selected record and source, not reused for another selection. This feature has only been tested with fake model responses, not the live event provider or the participant's Windows environment.

## Optional aggregate diagnostic

The independently written `tools/diagnose_paper_gates.py` reads the same bounded file tail and applies the observer's selection rules, then prints only counts for invalid records and fixed, allowlisted reason labels from the last 200 accepted records. Arbitrary reason text, symbols, account IDs, order IDs, credentials and raw records are not printed. Unknown reasons remain `OTHER_OR_UNKNOWN`. The known reason labels and their counts can still reveal information about a strategy: inspect the output before sharing it. The helper does not modify the bot, source ledger, cockpit snapshot, or `.env`, and makes no broker or model call. Since it reads at a separate instant, its counts can differ from the dashboard's polling snapshot.
