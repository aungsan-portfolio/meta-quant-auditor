# Synthetic Auditor Agent

The selected agent submission candidate on `agent-mode` starts from baseline
`af276a223f1bb916a281d55665c6e2276c5eefcb`. PR #7 remains a draft; promotion
remains subject to the checkpoint below. The agent selects JSON actions; local code
computes every gate, preserves history and compares supported claims. No broker, private
bot, shell, arbitrary URL, file upload or real account data is exposed as a model tool.

## Run and consent

Start the normal app from this branch and open **Auditor Agent**. **Start agent** opens
a short fictional-case summary and preview; it makes no provider request. Expand and
review the complete initial evidence, all scripted snapshots and the fixed instruction,
check consent, then press **Run consented agent**. A new run or scenario change requires
a fresh preview and explicit consent.
Only built-in fictional cases are accepted. Later requests send updated fictional
evidence and local tool outputs. The background worker publishes completed steps;
a Streamlit fragment refreshes the Plan / Act / Observe display every half second.
Each step shows the proposed action, a brief unverified reason, local validation and
a readable local result. Full action arguments and output are available in a collapsed
technical-details section. This is a decision/action trace, not private model reasoning.
The page shows the configured Baseten endpoint and requested model. Only responses
returned by the fixed endpoint worker receive the application-reported LIVE label;
custom/injected transports are marked unverified. This is not an independently signed
provider receipt. Each completed step also shows monotonic request and local-check
durations; the former includes context/worker overhead, not just provider inference.
Final claim rows show the full verification status first and omit the displayed index.

**Stop after current request** prevents the next request and discards a result arriving
after cancellation. **Refresh agent controls** refreshes the page controls after a run.
One job cannot start another run while its request is in flight. This is per UI session.

## Closed protocol

The model must return exactly `{"action": "...", "args": {}, "reason": "..."}`.
No native tool calling is used. The parser accepts bare JSON or one complete outer
JSON/unlabelled Markdown fence. It rejects surrounding prose, duplicate properties,
nonfinite numbers (including overflowing exponents), extra keys, oversized responses,
unknown actions and invalid args. `reason` is 1–500 characters and remains unverified.
The envelope limit is 12,000 characters. An action name can be used at most once.

| Action | Exact args | Local behavior |
| --- | --- | --- |
| `run_lifecycle_audit` | `{}` | Required first. Recompute G01/G02 quote checks, G03 lifecycle and G04 exposure/heat through the existing audit/memo code. |
| `query_order_status` | `{}` | Only when the local missing-evidence request needs a broker-order observation; append the scripted fictional snapshot. |
| `query_position` | `{}` | Only when a position observation is needed; append a fixed fictional quantity. |
| `query_protection` | `{}` | Only when protection is needed; append fixed fictional status/coverage. |
| `compare_claims` | `{"claims": [...]}` | Validate using the existing typed scalar/finding-code verifier and return its classifications. |
| `request_human_input` | `{}` | Stop with `NEEDS_INPUT` and the local evidence request. |
| `finish_report` | `{"claims": [...], "narrative": "..."}` | Recheck claims against the current report and attach a locally constructed memo. Narrative is unverified; contradictions/unknown claims require review. |

Claims use the existing `scope`, `event_id`, `field`, `value` closed format. One to 24
claims are accepted. Narrative is capped at 4,000 characters. Unknown evidence never
becomes a field match. Finishing with missing lifecycle evidence stops `NEEDS_INPUT`
without a final report. A finished run is a report, never trade authorization or a
claim that critical history is cleared. G01/G02/G04 can still be unknown or blocked.

Each run has at most 8 model requests/steps (lower test limits are allowed). Responses
are handled serially with no automatic retry, repair request or fallback model. Invalid
or repeated actions terminate. The query tools supply only local fixture values;
model-provided status/quantity/gate args are rejected. Unavailable snapshots stop
`NEEDS_INPUT`. Existing observations/findings are never rewritten by the model.

The existing fixed Baseten Meta endpoint/model are reused:
`meta-models/muse-spark-open-1026`. Each default HTTP request runs in a fixed Python
subprocess with a 30-second communication deadline. On timeout the parent kills and
drains that worker before returning failure; no next request is made. The key travels
over a private stdin pipe, not command-line args or the action context. Custom fake
transports in tests run in process and do not prove real provider timing. Process
startup/cleanup adds small overhead; this is not a hard real-time scheduling guarantee.

## Scripted scenarios

- `late_fill`: pending cancel → unsafe release → fill of 4, then position 4 and ACTIVE
  coverage 4. A later current G03 PASS retains both critical historical findings.
- `order_recovered`: an unavailable order query in the initial fictional trace, then
  a scripted CANCELED/zero-fill observation. Earlier unsafe-release history remains.
- `order_unavailable`, `position_unavailable`, `protection_unavailable`: the indicated
  tool returns `unavailable` and the run stops for human input.

These are on-demand scripted observations, not an independent market/broker stream.

## Ten-minute live spike

Local validation on October 31 (Linux/Python 3.12.14): **232 unit tests** passed with
ResourceWarning promoted to errors, and **14 Streamlit AppTest/network-guard checks**
passed. That includes 44 agent protocol/repeatability unit tests and 5 agent-page checks. Fake transports
exercise complete action runs; the subprocess startup test uses an empty key and
does not connect to the provider. These are not browser-visual or live-provider tests.

From this branch's repository root, with a local `.env` or environment key:

```powershell
.\.venv\Scripts\python.exe tools\run_agent_spike.py --consent --output reports\agent-spike.json
```

macOS/Linux: `.venv/bin/python tools/run_agent_spike.py --consent --output reports/agent-spike.json`.
The harness checks `late_fill` then `order_unavailable`, within a ten-minute window,
with the same per-call deadline and eight-step bound. It stops on the first failed
path. It writes status/action-name receipts without credentials or model prose into
the Git-ignored reports folder. `GO_PROTOCOL` means those two paths worked in that
particular run, not comprehensive safety. Offline tests also exercise this harness
using a fake transport; those results must not be presented as live Meta evidence.

To conduct the requested independent repetitions on Windows, review the fictional
scenarios and run the following **once** with a local key and explicit consent:

```powershell
.\.venv\Scripts\python.exe tools\run_agent_reliability.py --consent --runs-per-case 3 --output reports\agent-reliability.json
```

The command schedules three independent `late_fill` and three independent
`order_unavailable` runs (or 4–5 each when selected), at most eight serial requests per
run. These are pre-planned measurements, not retries within a failed run. All failed,
rejected and unavailable results remain in the receipt. The receipt distinguishes
protocol compliance, protocol violations, incomplete step-limited runs, undetermined transport failures, expected
scenario paths and claim-status counts. A completed path does not imply every claim
matched. It records UTC timestamps, source commit/clean state and response-source
telemetry, not model prose or credentials. A pre-existing output file is never
overwritten. A ten-minute start window is enforced, reserving 30 seconds for any new
request; an incomplete batch is reported as such. Six planned runs can send up to 48
provider requests and may consume credits. Offline fake-transport trials are not live
evidence.

**Participant-supplied Windows repeatability receipt, October 31:** On runtime commit
`eee6935439731989c61a5227197d349377c65f02`, with a clean tree at start and end, the
batch ran from 12:22:54 to 12:23:27 UTC (19:22:54–19:23:27 Thailand time). All three
`late_fill` runs finished with human review required; all three `order_unavailable`
runs stopped NEEDS_INPUT after the scripted snapshot was unavailable. Each scenario was
protocol-compliant and followed its expected path 3/3 times. The three completed reports
recorded 22, 18 and 23 selected claim matches, with no contradictions or unverified
claims. The batch recorded 18 provider requests and took 33.237 seconds. Response
origin was labelled live by the application, not independently attested. Claims are
compared with fictional evidence; narrative remains unverified. Six scripted trials
are a limited observation, not a guarantee of future model behavior.

**Participant-reported live records (October 31):** The first Windows spike was
NO_GO / MALFORMED_JSON on the first response of `late_fill`. After a prompt change, a
second spike finished `late_fill` in four actions with human review required, but the
first `order_unavailable` response was rejected as MALFORMED_JSON; its diagnostic
indicated a non-object/fence prefix and an error at the start; the combined result was
still NO_GO. On runtime commit `4228e98`, the third spike returned GO_PROTOCOL: the
`late_fill` case finished after four actions with human review required, and the
`order_unavailable` case stopped NEEDS_INPUT after its order query returned unavailable.
That entire two-scenario run took 12.838 seconds. This is the participant's receipt,
not an independent provider-network capture or Windows browser-visual review. A single
successful run does not establish a reliability rate. The earlier failures were on
earlier revisions and their response text was not retained. In this coding environment
a separate attempt returned NOT_RUN / KEY_MISSING without a request.

Participant-provided Windows screenshots show `late_fill` step cards, a final claim
table and the unverified-narrative warning, plus an `order_unavailable` stop at
NEEDS_INPUT. Later `late_fill` screenshots show the live label, per-step durations and
verification-first table; some long cells are clipped at the captured screen size.
The screenshots do not show preview, consent, intermediate updates or the exact commit.
A screenshot alone is not a provider network capture and does not establish every
claim status or future reliability.

The previewed context now includes a fixed request for one JSON action, in addition to
the system instruction and first-step example. The spike reports coarse diagnostic
categories for malformed output, including a prefix type when identifiable and whether
an object marker appears later. It never stores or prints response text, provider
errors, credentials, or model reasoning. These changes do not relax validation, repair
output or send another request. One run after the additional instruction succeeded,
but causation and future reliability are not established; earlier receipts cannot be
reclassified.

Baseten's [JSON mode documentation](https://docs.baseten.co/inference/json-mode) says
Muse Spark Open on Model APIs accepts `json_object` but does not constrain its output to
JSON. Its [structured-output documentation](https://docs.baseten.co/inference/structured-outputs)
likewise says `json_schema` is not enforced for Muse Spark Open. Those documents do not
separately establish behavior for the event-specific `-1026` identifier. The agent does
not rely on either feature: it prompts for JSON and validates the complete response
locally, rejecting invalid output without retry.

## Go/no-go checkpoint

Checkpoint: **Tuesday night, November 3, 2026, Thailand time (ICT)**. Keep this PR a
draft and preserve `main`, retaining the baseline as a fallback.
The participant-supplied `eee6935` repeatability receipt shows both paths passed 3/3
times each. Promote the agent demo only after: the selected commit's Linux/Windows CI
passes; Windows visual review confirms preview/consent and incremental trace; and a
recorded demo fits within three minutes. Assess repeatability in the visual run, with no automatic retries; a
failed run must remain visible. Otherwise retain the baseline presentation. The
organizer's confirmation that submissions remain editable until the deadline was
supplied by the participant.
