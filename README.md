# Meta Quant Auditor

[![Offline tests](https://github.com/aungsan-portfolio/meta-quant-auditor/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/aungsan-portfolio/meta-quant-auditor/actions/workflows/offline-tests.yml)

Meta Quant Auditor helps paper-trading developers and reviewers investigate why a risk check blocks or passes a candidate. It reconstructs fictional cancellation timelines, keeps unsafe history visible, and compares selected structured claims from Meta Muse Spark Open with the supplied evidence.

**Model proposes claims. Local code compares supported fields with evidence.** The main demo is a standalone workbench with built-in synthetic cases; the earlier trading bot is not needed to run it.

**Track:** Indie Developer candidate. **Theme:** Build for Your World.

## Start with one case

Run the app and open **Cancellation Safety**:

1. Select **Pending cancel → early release → late fill**. A reservation was released while cancellation was pending; a later fill exposes the unsafe sequence. Inspect the finding and its evidence events.
2. Add fictional position and protection follow-ups if requested. A later current PASS does not erase the critical history.
3. Under **Check structured claims against evidence**, click **Try fictional claims · no model**. The clearly labeled sample demonstrates `EVIDENCE_MATCH`, `CONTRADICTION`, and `UNVERIFIED`; it does not call an AI model.
4. For an actual Meta response, review the synthetic evidence and fixed instruction, then explicitly click **Ask Muse Spark for structured claims**. Local code compares supported scalar fields and recorded finding codes. The accompanying free-form interpretation remains unverified.

This lets a reviewer distinguish a claim that matches a supplied field, a contradiction, and a claim for which evidence is missing. Matching fictional fields does not establish real-world truth or verify the meaning of an entire explanation.

## What Meta adds

Runtime requests use **`meta-models/muse-spark-open-1026` through Baseten**. No other runtime model is configured. The model produces explanations or structured claims; deterministic code computes the audit findings independently. A slow, unavailable, or contradictory model response cannot change those findings.

The two structured-response verifiers accept bare JSON or one complete outer Markdown fence, optionally labeled `json`. They do not extract JSON from surrounding prose or repair truncated output. Original response-size limits, duplicate-property rejection, finite-number checks, closed schemas, and typed field comparisons remain in force. Unsupported or missing evidence never becomes a match merely because output is well formatted.

Model requests are explicit, run in the background, and have no automatic retries. They may consume provider credits. Empty, malformed, or truncated output is unavailable; the 30-second request timeout does not guarantee that a worker thread stops at exactly 30 seconds. The app does not automatically verify free-form model prose.

## Other views

| View | What to inspect |
| --- | --- |
| Home | Fictional quote freshness and spread checks; optional single-gate explanation. |
| Audit Workbench | Synthetic quote, account, chase, and duplicate checks with downloadable reports. |
| Trace Inspector | Contradictions in recorded synthetic gate results. |
| Cancellation Safety | Lifecycle evidence, missing-evidence follow-ups, bounded claim comparison, and a reviewable deterministic memo. |
| Paper Observation | A fictional step-through replay; an optional read-only view of selected operator-provided local gate records. |
| Risk Cockpit | Four illustrative checks on fabricated spread, chop, projected-exposure, and confidence inputs; sliders recalculate the checks and the model preview. |

For the cockpit exposure example, select **S&P 500 Afternoon Rotation**. Fictional GOOGL has projected exposure of 32.4%; a 28% demo cap yields `BLOCKED_EXPOSURE`, while a 35% demo cap lets the four displayed checks pass. `SIMULATED_PASS` is a result within those demo thresholds. Moving the slider does not change the separate bot's policy or authorize a trade. Confidence, ATR, and bracket values are fabricated examples, not executed XGBoost inference or live strategy telemetry.

## Run locally

Requirements: **Python 3.11 or later**, Git or an extracted copy, and internet access to install dependencies. Direct dependencies are pinned to **Streamlit 1.66.1** and **python-dotenv 1.2.4**. These pins were validated on Linux with Python 3.12.14; they are not a record of the versions used in the earlier Windows demo. Transitive dependencies are not fully locked.

### Windows

Open PowerShell in a separate checkout of this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS / Linux

Open a terminal in a separate checkout of this repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Keep the terminal open and visit the local URL shown by Streamlit. Built-in synthetic cases and offline claim examples work without an API key. The checked-in configuration binds the app to localhost.

To request a model explanation, create a local `.env` from `.env.example` and add your own Baseten key. An existing `BASETEN_API_KEY` environment variable takes precedence. Never include a real key in the repository, an archive, a screenshot, or chat.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s ui_tests -v
```

On macOS/Linux, use `.venv/bin/python` in place of the Windows interpreter path.

| Evidence | Scope and limits |
| --- | --- |
| 178 unit tests on the patched source | Passed in the local Linux/Python 3.12.14 review, including 11 response-envelope regressions. Tests use fake provider transports. |
| 8 real Streamlit AppTest checks and 1 network-guard regression | Exercise the entrypoint and all five pages, built-in cases, offline claims, follow-ups, cockpit recalculation, and consent reset with external connections blocked. Local loopback communication needed by Windows asyncio remains available. These are framework/widget checks, not browser visual tests or provider calls. |
| Earlier Windows evidence | The prior source passed 167 offline tests on Windows/Python 3.14. My earlier live checks covered single-gate and reported-paper-event explanations; a Windows cockpit screenshot also showed a live-runtime explanation. These limited observations do not validate every model path or the new dependency pins on Windows. |
| GitHub Actions | The workflow targets Linux and Windows on Python 3.11 and 3.14. Remote run results are available through the workflow link above; local checks are separate evidence. |

The available Windows record does not establish live-provider validation of the separate lifecycle structured-claim, Workbench replay, Trace Inspector, or cancellation narrative paths. Offline tests do not certify broker behavior or production safety.

## Data boundaries and limitations

Use built-in fictional examples for the shared demo. Supported JSON uploads must also be fictional and follow the [closed synthetic formats](docs/SYNTHETIC_FORMATS.md); a `synthetic` flag cannot prove an upload is safe.

- Audit pages send normalized allowlisted synthetic facts and checks after an explicit request, not the original uploaded file. The cockpit sends generated labels and synthetic numbers. Each request also includes a fixed instruction.
- The optional [local observer](docs/PAPER_OBSERVATIONS.md) does not import the old bot or contact a broker. It reads selected fields from an operator-provided ledger. Source, paper mode, and event-time provenance are operator-declared, not independently verified. Its optional model request sends four previewed categorical labels plus a fixed instruction after confirmation; labels can still be sensitive.
- Data minimization reduces disclosure risk; it is not an absolute zero-leakage guarantee. Keep private observation data local and out of public demos, archives, and hosted deployments.
- This is a research prototype using fictional audit cases. It has no broker integration or order execution and is not financial advice. Quote checks use a shared fictional snapshot; cancellation observations and supplied protection fields are case evidence, not proof of live broker state.
- Duplicate detection uses an in-memory simulation ledger, not durable or broker-side idempotency. The cockpit does not check freshness, daily loss, broker protection, or overall eligibility.
- Memo review actions are unauthenticated browser-session records. A fingerprint is not a signature or verified identity. Reviews disappear with the session unless downloaded; recording a review does not validate AI prose or authorize a trade.
- Plan → Act → Observe describes fixed application steps. The demo is not an autonomous model agent. Free-form explanations remain unverified even when some structured fields match.

## Provenance

My paper-trading bot and an earlier audit scaffold existed before the hackathon and remain separate. This public repository contains the standalone event demo and newly fabricated scenarios. [PROVENANCE.md](PROVENANCE.md) records the development boundary and limits of the evidence; file dates and a fresh Git history alone cannot prove eligibility.

**Pre-existing reference material:** The optional observer and diagnostic tool recognize selected source-field names, strategy/status names, and gate-label vocabulary from my earlier bot and its reported records. These names are used for input compatibility; they are not newly invented bot rules.

| Recognized pre-existing vocabulary | Event-window implementation | Current count |
| --- | --- | --- |
| Reported reason-code names | `auditor/paper_observer.py` · `REASONS` | 17 labels |
| Source stage names | `auditor/paper_observer.py` · `STAGES` | 21 input names mapped to 21 normalized stage labels |
| Diagnostic reason-code names | `tools/diagnose_paper_gates.py` · `SAFE_REASON_LABELS` | 36 labels, including all 17 observer reason labels |

The normalized event format, allowlist mappings, adapter, diagnostic implementation, UI, and tests were written during the event. The earlier bot's parser, strategy/execution implementation, private records, credentials, and Git history are not included. The built-in synthetic demo runs independently of that bot.

Cerebral Valley's general reply specifies disclosure, event-built demo features, a fresh public runnable repository, Meta-only runtime models, and a video of 3:00 or less. I have asked the organizers for a project-specific use-case ruling and am waiting for their response.

Dependencies are [Streamlit](https://github.com/streamlit/streamlit) and [python-dotenv](https://github.com/theskumar/python-dotenv), plus Python's standard library. Their source is not vendored. This repository uses the [MIT License](LICENSE); dependency licenses and event rules still apply.
