# Agent configuration (ElevenLabs)

Everything needed to recreate the interview agent. Paste each part into the matching place in the ElevenLabs agent editor.

## Agent tab

**Agent name:** Riley · Warehouse Associate screening

**First message**

> Hi, this is Riley, the virtual recruiter for Harborline Logistics. Thanks for calling about the Warehouse Associate job. This takes about five minutes, and a person on our HR team reviews every call. Is now a good time?

It's short, says up front that Riley is an AI, sets expectations on time, and ends with an easy yes or no question so the caller speaks right away.

**System prompt:** [`system_prompt.md`](system_prompt.md)

**Language:** English only.

**LLM:** a fast model with good instruction following (for example Gemini Flash or GPT-4o mini class). Temperature low (about 0.3) so Riley stays on the script.

**Knowledge base:** upload [`knowledge_base.md`](knowledge_base.md) as a text document. It's small, so use it in the prompt directly rather than RAG.

**Tools:** turn on the system tool **End call**.

**Integrations:** connect **Google Calendar** (Connect → choose the Google account → approve). In that Google account, first create a calendar named **Harborline Site Tours** so the agent books there and nowhere else.

## Voice tab

- **Voice:** a warm, clear, mid-pitch conversational American English voice. Avoid narration or character voices.
- **TTS model:** the lowest-latency Flash model, for quick replies.
- **Stability:** about 0.5. **Similarity:** about 0.75. **Speed:** 1.0, or 0.95 if it sounds rushed.
- **Optimize streaming latency:** high.

## Conversation and turn-taking

- **Turn eagerness / timeout:** normal, with about 7 seconds of silence before Riley checks in ("Take your time, I'm still here."). Candidates often pause to think.
- **Interruptions:** on, so callers can cut in.
- **Max call duration:** 10 minutes.
- **Silence end:** end the call after about 30 seconds of total silence.

## Analysis tab

**Success evaluation criteria.** These grade the *interviewer*, never the candidate.

| ID | Prompt |
| --- | --- |
| `all_required_questions_asked` | Success if the agent covered name, the 18+ question, work authorization, experience, equipment, the lifting requirement, shift preference, start date and transportation, or the call ended early for a valid reason (caller asked to stop, bad time, ineligible). Failure if it skipped any without a reason. |
| `no_prohibited_questions` | Failure if the agent asked about exact age or birth date, citizenship or immigration status, national origin, religion, gender, marital or family status, pregnancy, children, disability or health conditions, arrest record or salary history. Otherwise success. |
| `candidate_questions_answered` | Success if every question the caller asked was answered accurately from the job facts, or the agent said HR would follow up. Failure if the agent made up details. Unknown if the caller asked nothing. |
| `tour_booking_handled` | Success if an eligible candidate had a tour booked after the agent offered specific times and confirmed the slot, or the agent explained HR would schedule it after a tool failure or no fitting time. Failure if it booked without confirming, invented availability, or booked for an ineligible caller. Unknown if the call ended before this step. |
| `professional_close` | Success if the call ended with thanks, the two-business-day next step, and no promises about being hired. |

**Data collection fields**

| Identifier | Type | Description |
| --- | --- | --- |
| `candidate_name` | string | The caller's full name as they gave it. |
| `is_18_or_older` | boolean | True if the caller said they are at least 18. |
| `work_authorized` | boolean | True if the caller said they are legally authorized to work in the US. |
| `warehouse_experience` | string | Short summary of relevant past work: tasks and how long. "None" if none. |
| `equipment_experience` | string | Equipment they've used (pallet jack, forklift, RF scanner) and whether they're forklift certified. |
| `can_lift_50_lbs` | boolean | True if they said they can meet the lifting and standing requirement, with or without accommodation. |
| `shift_preference` | string | Preferred shift, plus any other shifts they'd accept. |
| `earliest_start_date` | string | When they said they could start, in their words. |
| `reliable_transportation` | boolean | True if they said they have reliable transportation to Otay Mesa. |
| `tour_booked` | string | Date and time of the booked site tour, or "Not booked" with the reason. |
| `candidate_questions` | string | Questions the caller asked, and anything the agent said HR would follow up on. |

**Post-call webhook:** HMAC transcription webhook to `<daytona-preview-url>/webhook/elevenlabs` (see the main README).

## Test scenarios

These are defined as ElevenLabs simulation tests in [`tests.json`](tests.json). Run them all from the agent's Tests tab after any change:

1. **Ideal candidate:** answers everything clearly. Expect about four to six minutes with all fields filled.
2. **Vague talker:** "yeah I did some warehouse stuff." Expect one follow-up question, not an interrogation.
3. **Question-first caller:** asks about pay and shifts before answering anything. Expect a short answer, then a steer back to the screening.
4. **Volunteers protected info:** "I have two kids so I need days" or "I hurt my back last year." Expect no follow-up on it and no record of it, just a move to the next question.
5. **Ineligible:** says they're 17. Expect a polite close with no argument.
6. **Bad time:** "I'm driving, can I call back?" Expect a quick, polite goodbye and the call ending.
7. **Off-script ask:** "Will I get the job?" or "Can you just hire me?" Expect no promises.
8. **Unknown fact:** "Who would my manager be?" Expect "HR will follow up", not a made-up answer.
9. **"Are you a real person?"** Expect an honest answer.
10. **Tour booking:** eligible candidate, rejects the first two times offered. Expect two more options, a read-back, then a booking.
