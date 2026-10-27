# Meta Quant Auditor — Synthetic Event Demo

Meta Quant Auditor helps a reviewer understand why a fictional quote was accepted or rejected by one audit gate. It shows the gate's deterministic outcome next to the evidence, and optionally asks Meta's Muse Spark Open model on Baseten to explain that same evidence in plain English.

This is a small standalone hackathon demo, not a trading bot, financial adviser, broker connection, or complete simulation engine. It uses fabricated data and thresholds. A single gate PASS is not a trade authorization or an overall eligibility decision. Model output can be wrong and must be checked against the displayed evidence.

## Demo flow

1. Choose **Wide spread**, **Stale quote**, **Within limits**, or **Unknown session**.
2. Inspect the quote freshness and spread quality gate outcomes and their limits.
3. Select a gate and expand **View the synthetic evidence sent to the model**.
4. With an eligible Baseten key configured locally, select **Explain selected event**. If the request is running, select **Refresh explanation status**. Compare the answer with the evidence.

The gate checks run without an API key. The optional model request uses `meta-models/muse-spark-open-1026`, `reasoning_effort=low`, and `max_tokens=1024`. It runs in the background and cannot alter gate outcomes. There is no automatic retry; explicit model calls may consume credits. The 30-second request timeout does not guarantee that a worker thread will terminate at precisely 30 seconds.

Only built-in synthetic evidence is sent to Baseten. No real market data, real account data, arbitrary uploads, broker integration, or order execution is included. Incomplete or truncated model output is reported as unavailable rather than displayed as a completed explanation.

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

These tests use fake transports and do not call Baseten. The participant reported successful live explanation responses in their Windows demo for G01 PASS, G01 BLOCK, and G02 VETO; those responses were shared in conversation, not independently reproduced by the preparer of this package. They do not certify other scenarios or production readiness. The separate project's T1–T7 requirements have not been certified here.

## Project provenance and dependencies

The prior trading bot and pre-event audit scaffold are background context and are not included. This standalone demo and its fictional scenarios were developed during the hackathon; see [PROVENANCE.md](PROVENANCE.md) for the limits of that statement.

External runtime dependencies are [Streamlit](https://github.com/streamlit/streamlit) and [python-dotenv](https://github.com/theskumar/python-dotenv), listed in `requirements.txt`; the project does not vendor their source. Python standard-library modules are also used. Review dependency licenses and event rules for your use.

This repository candidate is not an eligibility determination or a completed submission. The organizer's answer about the project's category was pending when it was prepared. Review the applicable official rules and accurately disclose pre-existing background in the demo video.
