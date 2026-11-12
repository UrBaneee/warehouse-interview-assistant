# Project facts

Reference sheet for the Warehouse Interview Assistant: what runs where, how it connects, and what has been tested. Last updated November 12, 2026.

Secrets (HR password, webhook secret, API keys) are never stored here.

## How it fits together

1. A candidate talks to the ElevenLabs agent **Warehouse Interview Assistant v2**.
2. The agent can book a video interview through its Google Calendar integration.
3. When the call ends, ElevenLabs sends the transcript and analysis to the report service on Daytona.
4. HR opens the report dashboard and signs in.

## ElevenLabs

| Item | Value |
| --- | --- |
| Live agent | Warehouse Interview Assistant v2 |
| Agent ID | `agent_0801m71th4d8e0wrthfg56y1zmce` |
| Original hackathon agent (kept as-is, not used) | `agent_5101m6yhjpycfpsv1k7g68zq5nzj` |
| Voice | Skye's cloned voice, Eleven v3 conversational |
| LLM | Gemini 3.5 Flash, temperature 0.4 |
| Turn taking | Turn V3 |
| Language | English only |
| Company and facts | Harborline Logistics (made up) |
| Post-call webhook | "Daytona Interview Reports live" (workspace default, HMAC) |
| Custom guardrails | All off. The template ones ended calls on harmless answers. |
| Calendar | Google Calendar integration: check availability, create event, list events |

Full configuration (prompt, procedure, knowledge base, analysis fields, tests) lives in [`agent/`](agent/).

## Daytona

| Item | Value |
| --- | --- |
| Sandbox ID | `690376fb-e55b-473d-901d-c7c38ae5f6f4` |
| Report dashboard | https://8001-690376fb-e55b-473d-901d-c7c38ae5f6f4.daytonaproxy01.net/ (user `hr`) |
| Webhook endpoint | same URL + `/webhook/elevenlabs` |
| Service folder | `~/hr-demo` (`interview_bridge.py`, `interviews.sqlite3`, `start.sh`, `bridge.log`) |
| Preview access | Public. The URL is permanent; the service still requires the HR password and a valid webhook signature. |
| Auto-stop | Disabled |
| Terminal shell | zsh |

**Restart the service** (paste into the Daytona terminal, then enter the HR password and webhook secret):

```sh
bash ~/hr-demo/start.sh
```

If the webhook secret is lost, ElevenLabs cannot show it again: create a new webhook with the same URL, set it as the workspace post-call webhook, delete the old one, and rerun the command above with the new secret.

## Testing

11 simulation tests in the v2 agent's **Tests** tab (definitions in [`agent/tests.json`](agent/tests.json)). They run inside ElevenLabs, not Daytona.

| Run | Tests | Result |
| --- | --- | --- |
| 1 (all) | 11 | 7 passed; 3 cut off by template guardrails, 1 agent mistake |
| Rerun 04, 06 after fixes | 2 | 2 passed |
| 2 (all, guardrails off, calendar on) | 11 | 8 passed; 3 small agent mistakes |
| Rerun 01, 04, 08 after fixes | 3 | 3 passed |

Every test has passed after its fix, but not yet all 11 in a single run. Click **Run All Tests** to confirm. One full run costs about 10,000 ElevenLabs credits.

Calendar booking was confirmed in tests 01 and 11: availability checks and event creation succeeded, booking test interviews on Nov 11 at 10 AM and Nov 13 at 3 PM Pacific (plus possibly one more from a rerun). Which Google calendar they landed on still needs checking, and they should be deleted before a demo.

## Optional: automated testing on Daytona (not built)

This would **not** move the tests off ElevenLabs.

- **Stays the same:** the 11 tests are still defined and run in ElevenLabs, still use ElevenLabs credits, and can still be run by hand.
- **Added:** a job on Daytona that triggers "Run All Tests" on a schedule or after prompt changes, and an "Agent health" page on the report dashboard showing pass counts, failures and reasons over time.
- **Value:** little for day-to-day use; a good portfolio story ("automated regression tests with a pass-rate history").
- **Cost:** an ElevenLabs API key stored in Daytona (entered by the owner), plus credits for every scheduled run.
- **Not recommended:** having Daytona play fake candidates in parallel sandboxes. It duplicates what ElevenLabs already does, for much more work.

## Before a demo

- Delete the test events from the interview calendar.
- Optionally delete the 3 hackathon reports (Nov 8) from their report pages; they show as "Unnamed candidate".
- Make one Preview call to v2 and confirm the report appears on the dashboard.
