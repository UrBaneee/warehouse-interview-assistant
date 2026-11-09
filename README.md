# Warehouse Interview Assistant

A voice screening assistant for logistics recruiters. An ElevenLabs agent conducts the interview and sends the transcript and analysis to a Python service running in Daytona. The service verifies the webhook signature, stores each conversation once in SQLite, and displays a password-protected report for human review.

## Run the report service

Requires Python 3.9+ and no external packages.

```sh
PORT=8001 python3 interview_bridge.py
```

Enter a report password of at least 12 characters and the ElevenLabs webhook signing secret at the hidden prompts. For noninteractive startup, supply `HR_PASSWORD` and `ELEVENLABS_WEBHOOK_SECRET` through your environment. Set `ELEVENLABS_AGENT_ID` to limit ingestion to one agent.

On Daytona, keep the sandbox running and create an HTTPS preview URL for port 8001. In ElevenLabs, configure an HMAC post-call webhook for transcription events at `/webhook/elevenlabs` on that URL, then assign it to the interview agent. Open `/health` to check whether the service has a signing secret. Run a fresh interview and open the preview root to view reports using username `hr` and your report password.

The public source contains the report service. The voice, interview procedure, knowledge base, and agent are configured separately in ElevenLabs. The demo does not score or rank applicants.
