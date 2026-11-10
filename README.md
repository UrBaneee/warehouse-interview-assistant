# Warehouse Interview Assistant

A voice screening assistant for logistics recruiters. An ElevenLabs agent runs a short phone-style interview for a Warehouse Associate role and sends the transcript and analysis to a small Python service running in Daytona. The service checks the webhook signature, stores each conversation once in SQLite, and gives HR a password-protected dashboard of interview reports.

Built in one afternoon at the SDx × SDSU voice agent hackathon (ElevenLabs + Daytona).

## What HR sees

- **Dashboard:** every interview with the candidate's name, a one-line summary, date, call length and whether the interview was completed.
- **Report:** the AI summary, structured candidate details (each with the reason the AI extracted it), interview quality checks that grade the *AI interviewer* rather than the candidate, and the full transcript. Reports print cleanly to PDF and can be deleted.

The demo does not score or rank applicants. A person reviews every call and makes all decisions.

## Run the report service

Requires Python 3.9+ and no external packages.

```sh
PORT=8001 python3 interview_bridge.py
```

Enter a report password of at least 12 characters and the ElevenLabs webhook signing secret at the hidden prompts. For noninteractive startup, set these environment variables:

| Variable | Purpose |
| --- | --- |
| `HR_PASSWORD` | Report password (12+ characters). Sign in as user `hr`. |
| `ELEVENLABS_WEBHOOK_SECRET` | HMAC signing secret from the ElevenLabs webhook settings. |
| `ELEVENLABS_AGENT_ID` | Optional. Only accept conversations from this agent. |
| `COMPANY_NAME`, `ROLE_NAME` | Optional. Shown in the report header. Defaults: Harborline Logistics, Warehouse Associate. |
| `PORT` | Defaults to 8000. |
| `INTERVIEW_DB` | Optional path for the SQLite file. |

## Deploy on Daytona

1. Keep the sandbox running and create an HTTPS preview URL for your port.
2. In ElevenLabs, add an HMAC post-call webhook for transcription events pointing at `<preview-url>/webhook/elevenlabs`, then assign it to the interview agent.
3. Open `/health` to confirm `"webhook_ready": true`.
4. Run a test interview, then open the preview root and sign in as `hr`.

No call handy? Send the bundled sample interview, signed the same way ElevenLabs signs it:

```sh
ELEVENLABS_WEBHOOK_SECRET=... python3 send_sample.py https://<preview-url>
```

## The agent

The voice, interview script, job facts and analysis settings live in ElevenLabs. [`agent/`](agent/) holds the full configuration so it can be reviewed and recreated: system prompt, first message, data collection fields, evaluation criteria, knowledge base and voice settings. The report reads whatever data collection fields the agent defines; a field named `candidate_name` is used as the report title.

## Security notes

- Webhooks are rejected unless the HMAC signature is valid and less than 30 minutes old.
- Reports sit behind HTTP basic auth over the Daytona HTTPS URL. Ten failed sign-ins from one client within five minutes trigger a temporary lockout.
- Deleting a report needs a per-report token, so another site can't trigger it.
- Request logging is off so candidate data and signed URLs don't end up in logs. The database file is created with owner-only permissions.

## Tests

```sh
python3 -m unittest discover -s tests
```
