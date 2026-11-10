"""Warehouse interview report service.

Run inside Daytona: python3 interview_bridge.py (Python standard library only).
Receives ElevenLabs post-call webhooks, stores each conversation once in SQLite,
and shows HR a password-protected dashboard of interview reports.
"""
import base64
from contextlib import contextmanager
import getpass
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DB = Path(os.environ.get('INTERVIEW_DB') or Path(__file__).resolve().with_name('interviews.sqlite3'))
SECRET = ''
PASSWORD = ''
AGENT_ID = ''
COMPANY = os.environ.get('COMPANY_NAME', 'Harborline Logistics')
ROLE = os.environ.get('ROLE_NAME', 'Warehouse Associate')

MAX_FAILURES = 10          # failed logins allowed per client ...
FAILURE_WINDOW = 300       # ... within this many seconds
SIGNATURE_TOLERANCE = 1800 # seconds; matches the ElevenLabs webhook window
CID_PATTERN = r'[A-Za-z0-9_-]{1,160}'
NAME_FIELDS = ('candidate_name', 'full_name', 'name')

_failures = {}
_failures_lock = threading.Lock()


# ---------- storage ----------

@contextmanager
def connect():
    """Open a connection, commit on success, and always close it."""
    db = sqlite3.connect(DB, timeout=15)
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS interviews (id TEXT PRIMARY KEY, received REAL, payload TEXT NOT NULL)')
    DB.chmod(0o600)


def save(event):
    data = event.get('data')
    if not isinstance(data, dict):
        raise ValueError('Missing data')
    cid = data.get('conversation_id', '')
    if not isinstance(cid, str) or not re.fullmatch(CID_PATTERN, cid):
        raise ValueError('Invalid conversation ID')
    if not isinstance(data.get('transcript', []), list):
        raise ValueError('Invalid transcript')
    with connect() as db:
        db.execute('INSERT OR IGNORE INTO interviews VALUES (?, ?, ?)', (cid, time.time(), json.dumps(data)))
    return cid


def load(cid):
    with connect() as db:
        row = db.execute('SELECT payload, received FROM interviews WHERE id=?', (cid,)).fetchone()
    if not row:
        return None
    data = json.loads(row[0])
    data.setdefault('conversation_id', cid)
    data['_received'] = row[1]
    return data


def delete(cid):
    with connect() as db:
        return db.execute('DELETE FROM interviews WHERE id=?', (cid,)).rowcount > 0


# ---------- security helpers ----------

def verify(raw, header, secret, now=None):
    """Check an ElevenLabs-Signature header of the form t=<unix>,v0=<hex hmac>."""
    if not secret:
        return False
    try:
        fields = dict(p.strip().split('=', 1) for p in header.split(','))
        stamp = fields['t']
        if abs((time.time() if now is None else now) - int(stamp)) > SIGNATURE_TOLERANCE:
            return False
        digest = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, fields['v0'])
    except (ValueError, KeyError):
        return False


def delete_token(cid):
    return hmac.new(PASSWORD.encode(), b'delete:' + cid.encode(), hashlib.sha256).hexdigest()


def locked_out(client, now=None):
    now = time.time() if now is None else now
    with _failures_lock:
        recent = [t for t in _failures.get(client, []) if now - t < FAILURE_WINDOW]
        _failures[client] = recent
        return len(recent) >= MAX_FAILURES


def record_failure(client, now=None):
    with _failures_lock:
        _failures.setdefault(client, []).append(time.time() if now is None else now)


# ---------- presentation helpers ----------

def esc(value):
    return html.escape(str(value))


def label(key):
    return str(key).replace('_', ' ').strip().capitalize()


def field_value(item):
    value = item.get('value') if isinstance(item, dict) else item
    if value is None or value == '':
        return 'Not provided'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def candidate_name(data):
    collected = (data.get('analysis') or {}).get('data_collection_results') or {}
    for key in NAME_FIELDS:
        item = collected.get(key)
        value = item.get('value') if isinstance(item, dict) else item
        if isinstance(value, str) and value.strip():
            return value.strip()
    return 'Unnamed candidate'


def started_at(data):
    meta = data.get('metadata') or {}
    stamp = meta.get('start_time_unix_secs') or data.get('_received') or 0
    try:
        return time.strftime('%b %d, %Y %H:%M UTC', time.gmtime(float(stamp)))
    except (TypeError, ValueError, OverflowError):
        return 'Unknown time'


def duration(data):
    secs = (data.get('metadata') or {}).get('call_duration_secs')
    if not isinstance(secs, (int, float)) or secs < 0:
        return '?'
    return f'{int(secs) // 60}:{int(secs) % 60:02d}'


def badge(result):
    result = str(result or 'unknown').lower()
    kind = {'success': 'ok', 'failure': 'bad'}.get(result, 'unk')
    text = {'success': 'Met', 'failure': 'Not met'}.get(result, 'Unclear')
    return f'<span class="badge {kind}">{text}</span>'


def call_badge(data):
    result = str((data.get('analysis') or {}).get('call_successful') or 'unknown').lower()
    kind = {'success': 'ok', 'failure': 'bad'}.get(result, 'unk')
    text = {'success': 'Completed', 'failure': 'Incomplete'}.get(result, 'Unclear')
    return f'<span class="badge {kind}">{text}</span>'


def snippet(data, limit=160):
    analysis = data.get('analysis') or {}
    text = analysis.get('call_summary_title') or analysis.get('transcript_summary') or ''
    text = ' '.join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


STYLE = '''
:root{--ink:#172033;--muted:#5b677a;--line:#e3e8ef;--bg:#f3f5f8;--accent:#1f5fd1}
*{box-sizing:border-box}body{font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--ink);margin:0}
header.top{background:var(--ink);color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
header.top b{font-size:17px}header.top span{color:#c6cfdd;font-size:14px}
main{max-width:1040px;margin:28px auto;padding:0 20px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:24px 28px;margin-bottom:20px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px}h2{font-size:18px;margin:0 0 14px}
a{color:var(--accent)}.muted{color:var(--muted)}.small{font-size:14px}
.meta{display:flex;flex-wrap:wrap;gap:8px 20px;color:var(--muted);font-size:14px;margin:6px 0 0}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;width:34%}thead th{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);width:auto}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
.list tbody tr:hover{background:#f7f9fc}
.badge{display:inline-block;font-size:12.5px;font-weight:600;padding:2px 10px;border-radius:99px;white-space:nowrap}
.ok{background:#e3f5ea;color:#17663a}.bad{background:#fde8e8;color:#9b1c1c}.unk{background:#eef1f5;color:#4a5568}
.why{display:block;color:var(--muted);font-size:13.5px;margin-top:3px}
.notice{background:#fff8e6;border:1px solid #f3dfa6;border-radius:10px;padding:10px 14px;font-size:14px;color:#6b5414}
.turn{display:flex;gap:12px;padding:10px 0}.who{flex:0 0 92px;font-size:13px;color:var(--muted);padding-top:9px}
.bubble{flex:1;padding:9px 14px;border-radius:12px;white-space:pre-wrap;overflow-wrap:anywhere}
.agent .bubble{background:#eef3fd}.user .bubble{background:#f1f2f4}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;font-size:14px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 14px;cursor:pointer}
button.danger{color:#9b1c1c;border-color:#f1c4c4}
.empty{text-align:center;padding:40px 0;color:var(--muted)}
@media print{body{background:#fff}header.top,.actions,.noprint{display:none}.card{border:0;padding:0}main{margin:0}}
'''


def page(title, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{STYLE}</style></head><body>'
            f'<header class="top"><b>{esc(COMPANY)} · Interview reports</b><span>{esc(ROLE)} screening</span></header>'
            f'<main>{body}</main></body></html>')


def dashboard(items):
    rows = ''
    for data in items:
        cid = data['conversation_id']
        rows += (f'<tr><td><a href="/reports/{esc(cid)}"><b>{esc(candidate_name(data))}</b></a>'
                 f'<span class="why">{esc(snippet(data) or "No summary yet")}</span></td>'
                 f'<td class="small">{esc(started_at(data))}</td><td class="small">{esc(duration(data))}</td>'
                 f'<td>{call_badge(data)}</td></tr>')
    if rows:
        table = (f'<table class="list"><thead><tr><th>Candidate</th><th>Date</th><th>Length</th><th>Status</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table>')
    else:
        table = '<p class="empty">No interviews yet. Reports appear here a minute or two after a call ends.</p>'
    count = f'{len(items)} interview{"s" if len(items) != 1 else ""}'
    return page('Interview reports', f'<div class="card"><h1>Interview reports</h1>'
                f'<p class="muted small">{count} · newest first · refresh after a call ends</p>{table}</div>')


def report(data):
    cid = data['conversation_id']
    analysis = data.get('analysis') or {}
    summary = analysis.get('transcript_summary') or 'No summary supplied by ElevenLabs. Review the transcript below.'

    collected = analysis.get('data_collection_results') or {}
    facts = ''
    for key, item in collected.items():
        why = item.get('rationale') if isinstance(item, dict) else ''
        facts += (f'<tr><th>{esc(label(key))}</th><td>{esc(field_value(item))}'
                  f'{f"<span class=why>{esc(why)}</span>" if why else ""}</td></tr>')
    facts = f'<table><tbody>{facts}</tbody></table>' if facts else '<p class="muted">No structured fields configured.</p>'

    criteria = analysis.get('evaluation_criteria_results') or {}
    checks = ''
    for key, item in criteria.items():
        item = item if isinstance(item, dict) else {'result': item}
        why = item.get('rationale') or ''
        checks += (f'<tr><th>{esc(label(item.get("criteria_id") or key))}</th><td>{badge(item.get("result"))}'
                   f'{f"<span class=why>{esc(why)}</span>" if why else ""}</td></tr>')
    checks_card = (f'<div class="card"><h2>Interview quality checks</h2><p class="muted small">How the AI interviewer did, '
                   f'not a rating of the candidate.</p><table><tbody>{checks}</tbody></table></div>') if checks else ''

    turns = ''
    for t in data.get('transcript', []):
        if isinstance(t, dict) and t.get('message'):
            role = 'agent' if t.get('role') == 'agent' else 'user'
            secs = t.get('time_in_call_secs')
            stamp = f'{int(secs) // 60}:{int(secs) % 60:02d}' if isinstance(secs, (int, float)) else ''
            who = 'Interviewer' if role == 'agent' else 'Candidate'
            turns += (f'<div class="turn {role}"><div class="who">{who}<br>{esc(stamp)}</div>'
                      f'<div class="bubble">{esc(t["message"])}</div></div>')
    turns = turns or '<p class="muted">No transcript available.</p>'

    body = f'''
<p class="noprint"><a href="/">← All interviews</a></p>
<div class="card">
  <h1>{esc(candidate_name(data))}</h1>
  <div class="meta"><span>{esc(ROLE)}</span><span>{esc(started_at(data))}</span><span>Length {esc(duration(data))}</span>{call_badge(data)}</div>
  <p class="notice" style="margin-top:16px">AI-generated summary. Candidate answers are self-reported. HR verifies facts and decides next steps; this report makes no hiring recommendation.</p>
  <div class="actions noprint">
    <button onclick="window.print()">Print or save as PDF</button>
    <form method="post" action="/reports/{esc(cid)}/delete" onsubmit="return confirm('Delete this interview permanently?')">
      <input type="hidden" name="token" value="{delete_token(cid)}"><button class="danger">Delete interview</button>
    </form>
  </div>
</div>
<div class="card"><h2>Summary</h2><p style="white-space:pre-wrap;margin:0">{esc(summary)}</p></div>
<div class="card"><h2>Candidate details</h2>{facts}</div>
{checks_card}
<div class="card"><h2>Full transcript</h2>{turns}<p class="muted small">Conversation ID {esc(cid)}</p></div>'''
    return page(f'{candidate_name(data)} · Interview report', body)


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    server_version = 'InterviewBridge'
    sys_version = ''

    def log_message(self, fmt, *args):
        # Avoid logging signed URLs or candidate data.
        pass

    def reply(self, code, body, kind='text/html; charset=utf-8', headers=()):
        raw = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def client(self):
        forwarded = self.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        return forwarded or self.client_address[0]

    def authorized(self):
        try:
            scheme, value = self.headers.get('Authorization', '').split(' ', 1)
            credentials = base64.b64decode(value, validate=True).decode()
            return scheme.lower() == 'basic' and hmac.compare_digest(credentials.encode(), ('hr:' + PASSWORD).encode())
        except (ValueError, UnicodeError):
            return False

    def gate(self):
        """Return True if the request may continue; otherwise send 401/429."""
        client = self.client()
        if locked_out(client):
            self.reply(429, 'Too many failed sign-ins. Try again in a few minutes.', 'text/plain; charset=utf-8',
                       [('Retry-After', str(FAILURE_WINDOW))])
            return False
        if self.authorized():
            return True
        if self.headers.get('Authorization'):
            record_failure(client)
        self.reply(401, 'Sign in required.', 'text/plain; charset=utf-8',
                   [('WWW-Authenticate', 'Basic realm="HR Reports", charset="UTF-8"')])
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.reply(200, json.dumps({'status': 'ok', 'webhook_ready': bool(SECRET)}), 'application/json')
        if not self.gate():
            return
        if path == '/':
            with connect() as db:
                rows = db.execute('SELECT id, received, payload FROM interviews ORDER BY received DESC').fetchall()
            items = []
            for cid, received, payload in rows:
                data = json.loads(payload)
                data.setdefault('conversation_id', cid)
                data['_received'] = received
                items.append(data)
            return self.reply(200, dashboard(items))
        match = re.fullmatch(rf'/reports/({CID_PATTERN})', path)
        if match:
            data = load(match.group(1))
            if data:
                return self.reply(200, report(data))
        self.reply(404, 'Not found', 'text/plain; charset=utf-8')

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == '/webhook/elevenlabs':
            return self.webhook()
        match = re.fullmatch(rf'/reports/({CID_PATTERN})/delete', path)
        if not match:
            return self.reply(404, 'Not found', 'text/plain; charset=utf-8')
        if not self.gate():
            return
        cid = match.group(1)
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            size = -1
        if not 0 < size <= 4096:
            return self.reply(400, 'Invalid request', 'text/plain; charset=utf-8')
        form = parse_qs(self.rfile.read(size).decode('utf-8', 'replace'))
        if not hmac.compare_digest(form.get('token', [''])[0], delete_token(cid)):
            return self.reply(403, 'Invalid delete token', 'text/plain; charset=utf-8')
        delete(cid)
        self.reply(303, '', headers=[('Location', '/')])

    def webhook(self):
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


def main():
    global PASSWORD, SECRET, AGENT_ID
    os.umask(0o077)
    PASSWORD = os.environ.get('HR_PASSWORD') or getpass.getpass('Choose HR report password (hidden): ')
    if len(PASSWORD) < 12:
        raise SystemExit('Use at least 12 characters for the report password.')
    SECRET = os.environ.get('ELEVENLABS_WEBHOOK_SECRET') or getpass.getpass('ElevenLabs webhook secret (Enter to configure later): ')
    # Leave this empty unless you have verified the exact Agent ID in your dashboard.
    AGENT_ID = os.environ.get('ELEVENLABS_AGENT_ID', '')
    port = int(os.environ.get('PORT', '8000'))
    initialize()
    print(f'HR bridge listening on port {port}. Reports: / ; webhook: /webhook/elevenlabs', flush=True)
    print('Webhook ready.' if SECRET else 'Webhook locked until restarted with the ElevenLabs signing secret.', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
