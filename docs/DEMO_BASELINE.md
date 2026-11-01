# Meta Quant Auditor demo

Target duration: **2:50**. The finished video must be **3:00 or less**. The timing below is a rehearsal target, not a measured video duration. Show the event-built standalone auditor with built-in fictional data.

## Before recording

- Open Cancellation Safety with **Pending cancel → early release → late fill** selected and no fictional follow-ups applied. Keep the local Baseten key configured without displaying it.
- Open the current successful GitHub Actions run in another tab. Close private logs, the earlier bot's source, and account views; clear taskbar hover previews.
- Rehearse the two fictional follow-ups below and the live structured-claim request. Provider latency varies. A prepared offline result is labeled as offline, and a prior provider response is labeled as a prior response; neither substitutes for the live request in this recording.

## Recording sequence

| Time | Screen and action | Spoken script |
| --- | --- | --- |
| 0:00–0:10 | Cancellation Safety title and built-in case. | My paper-trading bot and audit scaffold predate this event; I built this standalone auditor and Meta integration this week. |
| 0:10–0:30 | Show the lifecycle timeline and checklist. | I operate separate day and swing paper-trading bots and inspect their execution logs. This workbench checks cancellation sequences and preserves unsafe history. Unlike a snapshot rule checker, it compares Meta's individual claims with evidence and identifies missing facts. |
| 0:30–1:20 | Scroll the horizontal timeline right if needed; point to `E-003` pending cancel, `E-004` reservation release, and `E-005` late fill of 4. Under Missing lifecycle evidence, set **Fictional observed position quantity** to `4` and click **Add fictional follow-up and recheck**. Then set **Fictional protection status** to `ACTIVE` and **Fictional protection coverage quantity** to `4`, and submit again. Show current `PASS`, `CRITICAL HISTORY`, and `REVIEW_REQUIRED`. | Here, cancellation is pending when the reservation is released. A fill of four arrives afterward. Local code flags the unsafe sequence and requests missing evidence. I add fictional position and protection observations. The current cancellation check can now pass, but the critical history stays visible and the case still requires review. No broker action occurs. |
| 1:20–2:20 | Click **Reset fictional follow-ups** to return to the original built-in case. Open **Review evidence before sending**, then click **Ask Muse Spark for structured claims** in section 2b. If needed, click **Refresh structured claims**. Show the returned claim table and unverified-interpretation notice. | I return to the original case and review the synthetic evidence before sending it. This click makes a live request to Meta Muse Spark Open through Baseten. Local code compares supported fields and finding codes with the record. Each claim is marked EVIDENCE_MATCH, CONTRADICTION, or UNVERIFIED. A match means agreement with this fictional record, not real-world truth. The narrative remains unverified, and the model cannot change the gate. |
| 2:20–2:40 | Open Risk Cockpit and select **S&P 500 Afternoon Rotation**. Move **Max gross portfolio exposure cap (%)** from `28` to `35`. Show GOOGL changing from `BLOCKED_EXPOSURE` to `SIMULATED_PASS` and the updated JSON preview. | In the cockpit, changing the demo exposure cap from twenty-eight to thirty-five percent recalculates the fictional candidate and evidence preview locally. SIMULATED_PASS is within these demo thresholds; it does not authorize a trade. |
| 2:40–2:50 | Show the successful Linux/Windows CI matrix, then finish. | Offline unit and Streamlit checks run in Linux and Windows CI. Meta proposes claims; local code checks supported evidence. Thank you. |

The provider chooses the claims, so their number and results may vary; describe the table actually returned. The earlier Windows screenshot showed seven matches for the original case, which does not guarantee the next response. The cockpit explanation is an optional second provider request with its own preview and consent; the core live request in this script is the structured-claims call above.

The opening discloses the pre-existing bot and scaffold. The cases in this script are fictional, not actual bot events. If any events from the pre-existing paper-trading bot are shown in a different demo, clearly label them as originating from the pre-existing bot and identify their creation time separately. Selected field, strategy/status, and gate-label names used for compatibility also predate the event; the implementation boundary is detailed in the README and PROVENANCE. Add that vocabulary disclosure to the narration if those observer or diagnostic features are shown.

Rehearse with real click time and provider latency, inspect the exported video's actual duration, and stop around 2:50. If the live request fails or misses the recording window, resolve it and record again rather than presenting an offline sample as a live response.
