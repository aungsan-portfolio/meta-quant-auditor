# Draft: synthetic Auditor Agent demo

The agent version is the selected submission candidate. This is a rehearsal outline,
not a record of a completed video or promotion of the experimental branch. Meet the
[agent go/no-go checkpoint](AGENT_MODE.md#go-no-go-checkpoint) before release.
The finished video must be at most three minutes;
measure the exported duration and adjust the timing to actual provider latency.

Before recording, use this branch's app, configure the Baseten key securely, keep
private records and credentials off screen, and rehearse the `late_fill` case. The
preview and scripted snapshots contain fictional evidence. A provider request is
made only after explicit consent and can consume credits. Do not present a previous
trace, fake transport, or offline example as a live response.

| Target | Screen/action | Suggested narration |
| --- | --- | --- |
| 0:00–0:15 | Show the Auditor Agent page and fictional case. | My paper-trading bots and an earlier audit scaffold predate the hackathon. During the event I built this standalone synthetic auditor and Meta integration. |
| 0:15–0:35 | Select **Late fill · scripted position and protection available** and click **Start agent**. Show the fictional lifecycle preview. | I review paper-trading execution logs. Unlike a snapshot check, this follows a cancellation lifecycle and keeps an unsafe release visible after later evidence improves. These events are fictional. |
| 0:35–1:00 | Show the evidence, scripted snapshots and fixed instruction preview. | The agent can select from bounded actions. I review the fictional evidence and instruction before consenting to send them to Baseten. Queries use scripted snapshots, not a broker. |
| 1:00–2:05 | Check consent and click **Run consented agent**; show live Plan / Act / Observe steps and the returned result. | Meta Muse Spark Open proposes actions. Local code validates each action and calculates the gates. The trace shows what happened on this run; model reasons remain unverified. |
| 2:05–2:35 | Show final claim comparisons and retained critical history if the run produces them. | Local code compares supported structured claims with the fictional evidence. A match does not prove the model narrative or real-world truth; a current pass does not erase critical history. |
| 2:35–2:50 | Show the event-built action validation in `auditor/agent.py` and, if time permits, the relevant successful CI result. | Local code validates the proposed actions. This read-only prototype does not place orders or authorize trades. |

Describe the actual response and status shown. If the provider fails, stops for
input, or the run exceeds the time available, do not describe it as a completed
successful run; resolve the issue and record again. Do not hide the limitations or
claim that scripted observations are live broker data.
