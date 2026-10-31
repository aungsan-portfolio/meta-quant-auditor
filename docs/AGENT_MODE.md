# Experimental synthetic Auditor Agent

This draft on `agent-mode` starts from baseline `af276a223f1bb916a281d55665c6e2276c5eefcb`.
It is separate from the submitted baseline. The agent selects JSON actions; local code
computes every gate, preserves history and compares supported claims. No broker, private
bot, shell, arbitrary URL, file upload or real account data is exposed as a model tool.

## Run and consent

Start the normal app from this branch and open **Auditor Agent**. **Start agent** opens
the preview; it makes no provider request. Review the initial evidence, all scripted
snapshots and the fixed instruction, check consent, then press **Run consented agent**.
Only built-in fictional cases are accepted. Later requests send updated fictional
evidence and local tool outputs. The background worker publishes completed steps;
a Streamlit fragment refreshes the Plan / Act / Observe display every half second.
Each row shows the proposed action/args, a brief unverified reason, local validation
and local output. This is a decision/action trace, not private model reasoning.

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

Local validation on October 31 (Linux/Python 3.12.14): **216 unit tests** passed with
ResourceWarning promoted to errors, and **12 Streamlit AppTest/network-guard checks**
passed. That includes 28 new unit tests and 3 new agent-page checks. Fake transports
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

**Current live record (October 31): NOT_RUN / KEY_MISSING.** This coding environment
has neither a Baseten environment key nor a repo `.env`. No live request was made.
The event model's protocol adherence and provider latency remain unverified here.

## Go/no-go checkpoint

Checkpoint: **Tuesday night, November 3, 2026, Thailand time (ICT)**. Keep this PR a
draft and preserve `main` while the baseline submission proceeds in parallel.
Promote the agent demo only after: a real local-key spike passes both paths; the
Linux/Windows CI matrix passes; Windows visual review confirms preview/consent and
incremental trace; and a recorded demo fits within three minutes. Otherwise retain
the baseline presentation. The organizer's confirmation that submissions remain
editable until the deadline was supplied by the participant.
