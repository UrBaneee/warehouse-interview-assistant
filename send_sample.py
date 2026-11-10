"""Send the sample interview to a running report service, signed like ElevenLabs does.

Usage:
  ELEVENLABS_WEBHOOK_SECRET=... python3 send_sample.py [base_url] [payload.json]

Defaults: http://localhost:8000 and samples/sample_webhook.json.
Useful for demos and for checking a Daytona deployment without making a call.
"""
import hashlib
import hmac
import os
import sys
import time
import urllib.request
from pathlib import Path

base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
payload = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).with_name('samples') / 'sample_webhook.json').read_bytes()
secret = os.environ.get('ELEVENLABS_WEBHOOK_SECRET') or sys.exit('Set ELEVENLABS_WEBHOOK_SECRET first.')

stamp = str(int(time.time()))
signature = hmac.new(secret.encode(), stamp.encode() + b'.' + payload, hashlib.sha256).hexdigest()
request = urllib.request.Request(base + '/webhook/elevenlabs', data=payload, method='POST', headers={
    'Content-Type': 'application/json',
    'ElevenLabs-Signature': f't={stamp},v0={signature}',
})
with urllib.request.urlopen(request, timeout=15) as response:
    print(response.status, response.read().decode())
