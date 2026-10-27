# Meta Quant Auditor — Synthetic Audit Workbench

Meta Quant Auditor explores why a fictional paper-simulation attempt was blocked or passed checks. It replays multiple gates, inspects recorded synthetic gate results for contradictions, and optionally asks Meta's Muse Spark Open on Baseten to explain the evidence in plain English.

This is a small standalone hackathon demo, not a trading bot, financial adviser, broker connection, or complete simulation engine. It uses fabricated data and thresholds. A single gate PASS is not a trade authorization or an overall eligibility decision. Model output can be wrong and must be checked against the displayed evidence.

## What works now

1. In Streamlit's page navigation, open **Audit Workbench**. Replay a fictional case across quote freshness, spread, account state, chase and duplicate checks. Download its Markdown report or synthetic event trace JSON.
2. Open **Trace Inspector** and choose **Inconsistent spread record** to see a recorded PASS that conflicts with its observed value and limit. Alternatively, upload a synthetic trace downloaded from the workbench. The inspector reports `CONSISTENT`, `INCOMPLETE`, or `REVIEW_REQUIRED` and explains its checks.
3. On either page, review the explicitly allowlisted evidence, then optionally request a Muse Spark explanation. The model does not determine or change gate outcomes. Compare its text with the evidence; it can be wrong.
4. The original **app** home page remains available for inspecting the earlier single-gate examples.

The checks run without an API key. The optional model request uses `meta-models/muse-spark-open-1026`, `reasoning_effort=low`, and `max_tokens=1024` for a single gate or `1536` for a replay or trace review. It runs in the background. There is no automatic retry; explicit model calls may consume credits. The 30-second request timeout does not guarantee that a worker thread terminates at precisely 30 seconds.

The upload pages accept only the documented, closed synthetic JSON formats. Do not upload real accounts, orders, credentials, private information, or real market data: a `synthetic` flag alone cannot prove data is safe. After an explicit model request, only normalized allowlisted facts and checks are sent; the original uploaded file is not sent. Incomplete model output is reported as unavailable. See [the format and safety limitations](docs/SYNTHETIC_FORMATS.md).

**Current limitations:** The replay recalculates fictional checks from one shared quote snapshot; it is not a replay of the participant's existing bot. The trace inspector supports the new synthetic format only, not the pre-event bot's historical trace format. Its consistency checks cannot prove event provenance. Duplicate detection uses an in-memory simulation ledger, not persistent or broker-side idempotency. No broker integration or order execution exists. These features are a development increment, not a finished or production-ready hackathon submission.

## Run locally on Windows

Requirements: Python 3.10 or later, pip, and an internet connection to install dependencies. A Baseten key with access to the hackathon model is needed only for explanations.

Extract this project into its own new folder. Open PowerShell in that folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL shown by Streamlit. Keep the terminal open while using the app.

For model explanations, create a local `.env` from `.env.example` and enter your own Baseten key there. Never put a real key in code, screenshots, a public repo, a public archive, or chat. An existing `BASETEN_API_KEY` environment variable takes precedence over the local `.env` file. `.gitignore` is a precaution, not proof that a file is safe to publish; inspect the actual staged files and commit history.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use fake transports and do not call Baseten. The participant reported successful live explanation responses in the earlier single-gate Windows demo for G01 PASS, G01 BLOCK, and G02 VETO; those responses were shared in conversation. The newer replay and trace inspector pages have not yet been tested live with the provider or in the participant's Windows environment. The separate project's T1–T7 requirements have not been certified here.

## Project provenance and dependencies

The prior trading bot and pre-event audit scaffold are background context and are not included. This standalone demo and its fictional scenarios were developed during the hackathon; see [PROVENANCE.md](PROVENANCE.md) for the limits of that statement.

External runtime dependencies are [Streamlit](https://github.com/streamlit/streamlit) and [python-dotenv](https://github.com/theskumar/python-dotenv), listed in `requirements.txt`; the project does not vendor their source. Python standard-library modules are also used. Review dependency licenses and event rules for your use.

This repository candidate is not an eligibility determination or a completed submission. The organizer's answer about the project's category was pending when it was prepared. Review the applicable official rules and accurately disclose pre-existing background in the demo video.
