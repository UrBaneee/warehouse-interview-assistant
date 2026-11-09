"""Run inside Daytona: python3 interview_bridge.py (Python standard library only)."""
import base64
import getpass
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DB = Path(__file__).resolve().with_name('interviews.sqlite3')
SECRET = ''
PASSWORD = ''
AGENT_ID = ''

def connect():
    return sqlite3.connect(DB, timeout=15)

def initialize():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS interviews (id TEXT PRIMARY KEY, received REAL, payload TEXT NOT NULL)')
    DB.chmod(0o600)

def verify(raw, header, secret, now=None):
    if not secret:
        return False
    try:
        fields = dict(p.strip().split('=', 1) for p in header.split(','))
        stamp = fields['t']
        if abs((time.time() if now is None else now) - int(stamp)) > 1800:
            return False
        digest = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, fields['v0'])
    except (ValueError, KeyError):
        return False

def save(event):
    data = event.get('data')
    if not isinstance(data, dict):
        raise ValueError('Missing data')
    cid = data.get('conversation_id', '')
    if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', cid):
        raise ValueError('Invalid conversation ID')
    if not isinstance(data.get('transcript', []), list):
        raise ValueError('Invalid transcript')
    with connect() as db:
        db.execute('INSERT OR IGNORE INTO interviews VALUES (?, ?, ?)', (cid, time.time(), json.dumps(data)))
    return cid

def esc(value):
    return html.escape(str(value))

def page(title, body):
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>body{{font:16px/1.6 system-ui;background:#f1f5f9;color:#172033;max-width:1000px;margin:40px auto;padding:0 20px}}main{{background:white;border-radius:18px;padding:32px}}h1{{line-height:1.2}}a{{color:#245bcc}}article{{padding:14px 0;border-bottom:1px solid #e2e8f0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}.note{{color:#64748b}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}}@media print{{body{{background:white;margin:0}}}}</style><main>{body}</main></html>'''

def report(data):
    analysis = data.get('analysis') or {}
    summary = analysis.get('transcript_summary') or 'No summary supplied by ElevenLabs. Review the transcript below.'
    collected = analysis.get('data_collection_results') or {}
    rows = ''
    for key, value in collected.items():
        value = value.get('value', 'Not provided') if isinstance(value, dict) else value
        rows += f'<tr><th>{esc(key)}</th><td>{esc(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict,list)) else value)}</td></tr>'
    if not rows:
        rows = '<tr><td>No structured fields configured yet. The summary and full transcript are available.</td></tr>'
    turns = ''.join(f'<article><b>{esc(t.get("role", "unknown"))} · {esc(t.get("time_in_call_secs", ""))}s</b><pre>{esc(t.get("message") or "")}</pre></article>' for t in data.get('transcript', []) if isinstance(t, dict) and t.get('message'))
    return page('Interview report', f'<a href="/">← All interviews</a><h1>Warehouse interview report</h1><p>BBBBBB company · {esc(data["conversation_id"])}</p><p class="note">AI-generated summary; candidate statements are self-reported. HR verifies facts and decides next steps. No automated hiring recommendation.</p><h2>Conversation summary</h2><pre>{esc(summary)}</pre><h2>Collected information</h2><table>{rows}</table><h2>Full transcript</h2>{turns}')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Avoid logging signed URLs or candidate data.
        pass

    def reply(self, code, body, kind='text/html; charset=utf-8'):
        raw = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        try:
            scheme, value = self.headers.get('Authorization', '').split(' ', 1)
            credentials = base64.b64decode(value, validate=True).decode()
            return scheme.lower() == 'basic' and hmac.compare_digest(credentials.encode(), ('hr:' + PASSWORD).encode())
        except (ValueError, UnicodeError):
            return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.reply(200, json.dumps({'status': 'ok', 'webhook_ready': bool(SECRET)}), 'application/json')
        if not self.authorized():
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="HR Reports"')
            self.end_headers()
            return
        if path == '/':
            with connect() as db:
                items = db.execute('SELECT id, received FROM interviews ORDER BY received DESC').fetchall()
            body = ''.join(f'<article><a href="/reports/{esc(cid)}">{esc(cid)}</a><p class="note">Received {esc(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(stamp)))}</p></article>' for cid, stamp in items)
            return self.reply(200, page('HR interviews', '<h1>HR interview reports</h1><p>Refresh after your call ends and ElevenLabs finishes analysis.</p>' + (body or '<p>No interviews received yet.</p>')))
        if path.startswith('/reports/'):
            with connect() as db:
                row = db.execute('SELECT payload FROM interviews WHERE id=?', (path.removeprefix('/reports/'),)).fetchone()
            if row:
                return self.reply(200, report(json.loads(row[0])))
        self.reply(404, 'Not found')

    def do_POST(self):
        if urlsplit(self.path).path != '/webhook/elevenlabs':
            return self.reply(404, 'Not found')
        if not SECRET:
            return self.reply(503, 'Webhook secret not configured')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 5_000_000:
                return self.reply(413, 'Invalid payload size')
            raw = self.rfile.read(size)
            if not verify(raw, self.headers.get('ElevenLabs-Signature', ''), SECRET):
                return self.reply(401, 'Invalid signature')
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise ValueError('Invalid event')
            if event.get('type') != 'post_call_transcription':
                return self.reply(200, 'Ignored')
            if AGENT_ID and (event.get('data') or {}).get('agent_id') != AGENT_ID:
                return self.reply(200, 'Ignored different agent')
            save(event)
        except (ValueError, TypeError):
            return self.reply(400, 'Invalid event')
        except sqlite3.Error:
            return self.reply(503, 'Storage unavailable; retry delivery')
        self.reply(200, 'Report saved')

if __name__ == '__main__':
    os.umask(0o077)
    PASSWORD = os.environ.get('HR_PASSWORD') or getpass.getpass('Choose HR report password (hidden): ')
    if len(PASSWORD) < 12:
        raise SystemExit('Use at least 12 characters for the report password.')
    SECRET = os.environ.get('ELEVENLABS_WEBHOOK_SECRET') or getpass.getpass('ElevenLabs webhook secret (Enter to configure later): ')
    # Leave this empty unless you have verified the exact Agent ID in your dashboard.
    AGENT_ID = os.environ.get('ELEVENLABS_AGENT_ID', '')
    initialize()
    print('HR bridge listening on port 8000. Reports: / ; webhook: /webhook/elevenlabs', flush=True)
    print('Webhook ready.' if SECRET else 'Webhook locked until restarted with the ElevenLabs signing secret.', flush=True)
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8000'))), Handler).serve_forever()
