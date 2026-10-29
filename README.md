# Meta Quant Auditor — Synthetic Audit Workbench

Meta Quant Auditor explores why a fictional paper-simulation attempt was blocked or passed checks. It replays multiple gates, inspects recorded synthetic gate results for contradictions, and optionally asks Meta's Muse Spark Open on Baseten to explain the evidence in plain English. A separate, local-only observation page can display a limited, sanitized subset of user-declared pre-existing paper-bot gate records and, only after explicit review and approval, request an explanation of selected categorical labels.

This is a small standalone hackathon demo, not a trading bot, financial adviser, broker connection, or complete simulation engine. Its audit examples use fabricated data and thresholds. Its optional local gate observer displays reported records and does not verify paper mode or broker state. A single gate PASS is not a trade authorization or an overall eligibility decision. Model output can be wrong and must be checked against the displayed evidence.

**Proposed track:** Indie Developer. **Theme:** Build for Your World.

## Problem and domain context

The project is motivated by the author's experience building a separate paper-trading bot and needing to understand why its risk checks reject actions. The new auditor focuses on evidence a reviewer can inspect: it reconstructs fictional cancellation and late-fill timelines, keeps historical findings after later observations, requests missing evidence, and compares supported model claims with supplied fields. These checks do not establish what actually happened at a broker.

The earlier bot remains separate and is not required to run the built-in synthetic demo. An optional local, read-only adapter can observe selected records from an operator-provided ledger as described in [the local setup](docs/PAPER_OBSERVATIONS.md). The source, paper mode, and event-time provenance are not independently verified.

## What works now

1. In Streamlit's page navigation, open **Cancellation Safety**. The first fictional example records a reservation release while an order is pending cancel and then a later fill. The offline G03 audit marks the unsafe release and points to its evidence events. Compare with **Cancel confirmed with zero fill** and **Broker query unavailable**.
2. On the same page, choose **Exposure and heat exceed caps** to inspect G04. Gross exposure uses absolute supplied market values; stop-risk heat uses separately supplied risk-to-stop values. Both are percentages of supplied equity and use fictional caps.
3. Open **Audit Workbench** for fictional quote, account and duplicate checks, and **Trace Inspector** for recorded synthetic gate contradictions. Download evidence reports or synthetic JSON examples.
4. On each page, review the allowlisted evidence, then optionally request a Muse Spark explanation. The model does not determine or change gate outcomes. Compare its text with the evidence; it can be wrong. The original **app** home page remains available for the earlier single-gate examples.
5. In **Cancellation Safety**, the checklist displays G01–G04 together, while the lifecycle table preserves the evidence timeline. The Plan → Act → Observe summary describes fixed app steps; it is not an autonomous model-agent or model tool-use log.
6. A reviewer can inspect a model-free structured memo, acknowledge the fictional scope, mark the memo reviewed, or flag it for manual review. A downloadable record is bound to the current memo fingerprint. It is an unauthenticated browser-session action, not a digital signature, verified identity, trade authorization, or automatic validation of AI prose. Changing the evidence creates a different memo and requires another review. Reviews disappear with the session unless downloaded.
7. **Missing lifecycle evidence** identifies G03 conditions such as unknown broker status, non-terminal cancellation, or missing position/protection observations. It can append a fictional follow-up in the session and recompute the case. A later current PASS never erases historical warning or critical findings; the workflow has no broker connection. The follow-up is a new synthetic event, not proof of an actual order.
8. **Check structured claims against evidence** offers an offline, explicitly fictional example and an optional Muse Spark request. Local code compares supported scalar fields and recorded finding codes with a revalidated synthetic report, producing `EVIDENCE_MATCH`, `CONTRADICTION`, or `UNVERIFIED` per claim. Missing or invalid data never becomes a match. Free-form interpretation is always unverified; field matches do not establish semantic correctness, completeness, real-world truth, or trade safety. No model is called for the offline example.
9. **Paper event cockpit** displays a step-through fictional replay without credentials. An optional separate local observer reads a user-selected gate ledger and writes an allowlisted snapshot; the page polls that snapshot without contacting a broker. The records are labeled as reported by a pre-existing paper bot, not work built during the event, and paper mode and provenance are operator-declared. A reason summary counts reported reject/block records, using a finite allowlist expanded after the participant shared aggregate diagnostic results. Labels are not independent proof of the underlying inputs or actions. The observer does not supply live prices, authenticated fills, positions, stop coverage, or account balances. See [local observation instructions and limits](docs/PAPER_OBSERVATIONS.md).
10. **Explain one reported gate** is an optional, explicitly approved Muse Spark request for a fictional or local reported event. The preview shows the exact four categorical facts sent: source kind, stage, decision and reason. No symbol, strategy, timestamp, account, order ID, price, quantity or raw log is sent. A fixed system instruction is also sent; labels can still be sensitive. Local checks compare three structured model claims with the selected reported labels. Contradictory or unknown source-label claims withhold the narrative; other narrative remains unverified. A field match does not verify the source, broker, policy or meaning. No model call is automatic. The participant reported exercising one fictional and one operator-declared local paper-record explanation on Windows with the live provider; those limited checks do not establish broker truth or comprehensive provider coverage.

The checks run without an API key. The application's model requests use Meta's `meta-models/muse-spark-open-1026` through Baseten; no other runtime model is configured. A live model request requires the operator's key and an explicit action in the app. Requests use `reasoning_effort=low` and `max_tokens=1024` for a single gate or `1536` for a replay, trace review, cancellation audit or structured claim request. They run in the background. The claims request asks for a JSON-shaped text response without native JSON-mode parameters; malformed, empty or truncated responses are unavailable, not verified. There is no automatic retry; explicit model calls may consume credits. The 30-second request timeout does not guarantee that a worker thread terminates at precisely 30 seconds.

The existing audit upload pages accept only the documented, closed synthetic JSON formats. Do not upload real accounts, orders, credentials, private information, or real market data there: a `synthetic` flag alone cannot prove data is safe. After an explicit model request on those pages, only normalized allowlisted synthetic facts and checks are sent; the original uploaded file is not sent. Incomplete model output is reported as unavailable. See [the format and safety limitations](docs/SYNTHETIC_FORMATS.md). The separate paper observer does not send data automatically. If the operator explicitly approves a request, the four previewed categorical labels and a fixed instruction are sent to Baseten; these labels can still be sensitive and require review.

**Current limitations:** The quote replay recalculates fictional checks from one shared quote snapshot; the cancellation page consumes fictional observations and does not control or fix a trading bot. Synthetic protection fields are claims in a case, not proof of a correctly linked live stop. The trace pages support new synthetic formats only, not the pre-event bot's historical trace format. Their checks cannot prove event provenance. The reviewer action does not establish that a person actually reviewed the evidence, and the memo fingerprint is not an authenticated signature. Duplicate detection uses an in-memory simulation ledger, not persistent or broker-side idempotency. No broker integration or order execution exists. These features are a development increment, not a finished or production-ready hackathon submission.

## Run locally on Windows

Requirements: Python 3.10 or later, pip, and an internet connection to install dependencies. A Baseten key with access to the hackathon model is needed only for explanations.

Extract this project into its own new folder. Open PowerShell in that folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL shown by Streamlit. Keep the terminal open while using the app. The checked-in Streamlit configuration binds the app to localhost; do not expose the local observation page to a network or cloud service when it contains private data.

For model explanations, create a local `.env` from `.env.example` and enter your own Baseten key there. Never put a real key in code, screenshots, a public repo, a public archive, or chat. An existing `BASETEN_API_KEY` environment variable takes precedence over the local `.env` file. `.gitignore` is a precaution, not proof that a file is safe to publish; inspect the actual staged files and commit history.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use fake transports and do not call Baseten. The participant reported 155 tests passing on Windows at commit `f403ea4` without resource warnings; that checkout also contained untracked local source and test files which are not part of this repository. A separate development run of the committed tree passed 151 tests. The participant reported earlier single-gate live explanations and subsequently exercised the paper-record model path with one fictional and one operator-declared local record. Windows screenshots also showed the reason summary and the synthetic cancellation follow-up retaining critical history; they did not establish broker truth or a submitted review action. The separate lifecycle structured-claim model request has not yet been confirmed with a live provider on Windows. The separate project's T1–T7 requirements have not been certified here.

## Project provenance and dependencies

The prior trading bot and pre-event audit scaffold are background context and are not included. This standalone demo and its fictional scenarios were developed during the hackathon; see [PROVENANCE.md](PROVENANCE.md) for the limits of that statement.

External runtime dependencies are [Streamlit](https://github.com/streamlit/streamlit) and [python-dotenv](https://github.com/theskumar/python-dotenv), listed in `requirements.txt`; the project does not vendor their source. Python standard-library modules are also used. Review dependency licenses and event rules for your use.

This repository candidate is not an eligibility determination or a completed submission. The organizer's answer about the project's category was pending when it was prepared. Review the applicable official rules and accurately disclose pre-existing background in the demo video.
