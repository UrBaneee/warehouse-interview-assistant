# Agent configuration (ElevenLabs)

The live interview agent is **Warehouse Interview Assistant v2** in ElevenLabs. This folder holds everything needed to review or recreate it.

| File | Where it goes in ElevenLabs |
| --- | --- |
| [`system_prompt.md`](system_prompt.md) | Agent → System prompt |
| [`procedure.md`](procedure.md) | Procedures → "Warehouse screening interview" → Content (trigger: when the conversation begins) |
| [`knowledge_base.md`](knowledge_base.md) | Knowledge Base → two text documents |
| [`tests.json`](tests.json) | Tests → 11 simulation tests |

**First message**

> Hi, I'm Harborline Logistics' AI recruiting assistant, speaking with Skye's authorized voice. Are you ready to begin your warehouse interview?

## The scenario

An on-site Warehouse Associate role at Harborline Logistics (a made-up company): 6 AM to 2 PM shift where associates can leave early but must return within 45 minutes if called back before 2 PM, five locations (San Francisco, Atlanta, San Diego, Chicago, Edison), no relocation help, sponsorship questions handled without judging eligibility, and a preferred three-week start window. The agent never probes into work history, so every candidate gets the same practical questions.

## Settings

- **Voice:** Skye's cloned voice, Eleven v3 conversational TTS.
- **LLM:** Gemini 3.5 Flash, temperature 0.4.
- **Turn taking:** Turn V3, 7-second turn timeout.
- **Tools:** end call, skip turn, and Google Calendar (for booking the video interview on a "Harborline Interviews" calendar).
- **Post-call webhook:** HMAC webhook to the Daytona report service (`/webhook/elevenlabs`).

## Analysis

**Data collection (shown on each report):** `candidate_name`, `current_area`, `preferred_location`, `open_to_relocation`, `schedule_arrangement_ok`, `schedule_concerns`, `work_authorized`, `needs_sponsorship`, `earliest_start_date`, `video_interview_booked`, `candidate_questions`, `follow_up_needed`.

**Quality checks (grade the interviewer, never the candidate):** All topics covered · No probing into experience · No prohibited questions · No invented facts · Booking handled correctly · Accurate recap and close.

## Lessons from v1

Both failed calls in v1 were stopped by custom guardrails copied from a user-research template ("No leading questions" and "No roadmap promises"), each set to end the call. A candidate asking about her onboarding date was enough to trigger one. Template guardrails should be reviewed before an agent goes live, and "end call" is a harsh action for anything other than abuse.
