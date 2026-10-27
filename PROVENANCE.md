# Provenance and project boundary

## Prior background

The participant had a trading bot and an audit scaffold before the hackathon. They supplied domain context and ideas for the project. The pre-event bot, audit parser, schema, fixtures, tests, and Git history are not included in this candidate. The bot remains a separate project.

## Work prepared during the event

On October 27, 2026, a standalone demo was prepared in an isolated workspace. It began with fictional quote scenarios, two deterministic gate checks, a Streamlit interface, a Baseten/Muse Spark explanation client, and offline tests. Later event-window increments added separately written synthetic formats, simulation replay, consistency checks, report exports, additional Streamlit pages, a structured synthetic memo, a session-local reviewer action and offline tests. The cancellation audit and reviewer workflow were independently written during the event using general order-state and review concepts; their scenarios are newly fabricated and do not contain pre-event bot code or data. The workshop handbook was consulted for general ideas; its code and examples were not copied into this workflow. The source uses the participant's Baseten event instructions for the endpoint and model name. Development tools, Python and third-party packages were used; the packages are dependencies rather than vendored code.

The candidate was assembled from the event demo files available to the preparer. The participant's separate Windows working folder could have changed independently and cannot be inspected from this workspace. File comparison and secret scans are useful checks but cannot prove authorship, completeness, or hackathon eligibility. The organizer's answer on this project category was pending at preparation time.

## Live-test record

The participant reported successful model explanations for a fresh quote (G01 PASS), a stale quote (G01 BLOCK), and a wide spread (G02 VETO) in the original single-gate Windows demo. These are participant-reported observations from conversation. The newer replay, trace inspector and cancellation pages have not yet been tested live with Baseten or in the participant's Windows environment. The project does not include live logs or credentials; offline tests use fake transports.

## Suggested honest demo opening

> My trading bot and early audit ideas existed before the event. This standalone synthetic audit demo, its scenarios, and its Meta model interface were built during the hackathon.

Use this line only after confirming it accurately describes the final submission. Do not present simulated output as a live provider response. Neither this document nor a fresh Git history on its own establishes eligibility; the event organizers determine that under the applicable rules.
