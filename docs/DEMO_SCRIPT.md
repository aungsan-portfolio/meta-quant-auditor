# Synthetic Auditor Agent demo

The Auditor Agent is the selected demo on `main`, promoted through PR #7 after the
[checkpoint completed on November 1, 2026](AGENT_MODE.md#gono-go-checkpoint).
The recording reviewed that day measured **2:40.214** and the participant confirmed
preview, consent and incremental steps in Windows. This outline guides the selected
flow; the timings are approximate targets, not exact timestamps of every recorded
frame. The closing below is the target for the requested wording revision, not a
claim that replacement narration has already been recorded. Any later export must
remain at most three minutes; public video hosting and submission are separate tasks.

Before recording, use the app on `main`, configure the Baseten key securely, keep
private records and credentials off screen, and rehearse the `late_fill` case. The
preview and scripted snapshots contain fictional evidence. A provider request is
made only after explicit consent and can consume credits. Do not present a previous
trace, fake transport, or offline example as a live response.

| Target | Screen/action | Suggested narration |
| --- | --- | --- |
| 0:00–0:18 | Show the Auditor Agent page and fictional case. | My paper-trading bots and an earlier audit scaffold predate the hackathon. During the event I built this standalone synthetic auditor and Meta integration. |
| 0:18–0:35 | Introduce the domain and lifecycle-specific checks. | I review paper-trading execution logs. Unlike a snapshot check, this follows a cancellation lifecycle and keeps unsafe history visible. |
| 0:35–1:08 | Select **Late fill · scripted position and protection available**, click **Start agent**, review the preview, check consent and click **Run consented agent**. | These events are fictional. I can review the evidence and fixed instruction. The model has seven allowed actions; queries return scripted snapshots, not broker data. |
| 1:08–1:28 | Show the live Plan / Act / Observe trace and returned status. | This is a live call to Muse Spark Open. It finished, but it still needs human review. |
| 1:28–1:54 | Inspect the audit, position and protection steps. | The model proposes actions. Local code validates them and computes the gate. Position and protection evidence can improve the current status, but critical history still needs review. |
| 1:54–2:09 | Show final claim comparisons and the unverified-narrative notice. | Local code checks supported claims against the fictional record. A field match does not verify narrative or real-world truth. |
| 2:09–2:32 | Select **Unknown order · order snapshot unavailable**. Preview, consent and run; show NEEDS_INPUT after the query. | Here, order evidence is unavailable. The agent stops for input instead of inventing it. |
| 2:32–2:40 | Hold the stopped-run result and close. | The model chooses the steps. The code checks the claims. Thank you. |

Describe the actual response and status shown. If the provider fails, stops for
input, or the run exceeds the time available, do not describe it as a completed
successful run; resolve the issue and record again. Do not hide the limitations or
claim that scripted observations are live broker data.
