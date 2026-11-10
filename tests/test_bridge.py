"""Run with: python3 -m unittest discover -s tests"""
import base64
import hashlib
import hmac
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import interview_bridge as bridge  # noqa: E402

SAMPLE = (ROOT / 'samples' / 'sample_webhook.json').read_bytes()
SECRET = 'whsec_test_secret'
PASSWORD = 'correct horse battery'


def sign(raw, secret=SECRET, stamp=None):
    stamp = str(int(time.time()) if stamp is None else stamp)
    digest = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    return f't={stamp},v0={digest}'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class VerifyTests(unittest.TestCase):
    def test_valid_signature(self):
        self.assertTrue(bridge.verify(SAMPLE, sign(SAMPLE), SECRET))

    def test_wrong_secret(self):
        self.assertFalse(bridge.verify(SAMPLE, sign(SAMPLE, 'other'), SECRET))

    def test_tampered_body(self):
        self.assertFalse(bridge.verify(SAMPLE + b' ', sign(SAMPLE), SECRET))

    def test_stale_timestamp(self):
        self.assertFalse(bridge.verify(SAMPLE, sign(SAMPLE, stamp=time.time() - 3600), SECRET))

    def test_garbage_header_and_missing_secret(self):
        for header in ('', 'nonsense', 't=abc,v0=1', 'v0=deadbeef'):
            self.assertFalse(bridge.verify(SAMPLE, header, SECRET))
        self.assertFalse(bridge.verify(SAMPLE, sign(SAMPLE), ''))


class RenderTests(unittest.TestCase):
    def setUp(self):
        bridge.PASSWORD = PASSWORD
        self.data = json.loads(SAMPLE)['data']

    def test_report_shows_key_information(self):
        page = bridge.report(self.data)
        for text in ('Marcus Delgado', 'Swing (nights also OK)', 'Interview quality checks', 'Met', '1:54', 'Delete interview'):
            self.assertIn(text, page)
        self.assertNotIn('BBBBBB', page)

    def test_report_escapes_candidate_text(self):
        self.data['transcript'].append({'role': 'user', 'message': '<script>alert(1)</script>'})
        self.data['analysis']['data_collection_results']['candidate_name']['value'] = '<b>x</b>'
        page = bridge.report(self.data)
        self.assertNotIn('<script>alert', page)
        self.assertNotIn('<b>x</b>', page)

    def test_report_survives_missing_analysis(self):
        page = bridge.report({'conversation_id': 'c1', 'transcript': []})
        self.assertIn('Unnamed candidate', page)
        self.assertIn('No summary supplied', page)

    def test_field_values(self):
        self.assertEqual(bridge.field_value({'value': True}), 'Yes')
        self.assertEqual(bridge.field_value({'value': False}), 'No')
        self.assertEqual(bridge.field_value({'value': None}), 'Not provided')


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        bridge.DB = Path(cls.tmp.name) / 'test.sqlite3'
        bridge.SECRET, bridge.PASSWORD, bridge.AGENT_ID = SECRET, PASSWORD, ''
        bridge.initialize()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), bridge.Handler)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        bridge._failures.clear()

    def request(self, path, data=None, headers=None, auth=PASSWORD, client='10.0.0.1'):
        headers = dict(headers or {})
        headers['X-Forwarded-For'] = client
        if auth is not None:
            headers['Authorization'] = 'Basic ' + base64.b64encode(f'hr:{auth}'.encode()).decode()
        req = urllib.request.Request(self.base + path, data=data, headers=headers)
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=5) as resp:
                return resp.status, resp.read().decode(), resp.headers
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode(), err.headers

    def post_webhook(self, raw, signature=None):
        return self.request('/webhook/elevenlabs', raw, {'ElevenLabs-Signature': signature or sign(raw)}, auth=None)

    def test_health_is_public(self):
        status, body, _ = self.request('/health', auth=None)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['webhook_ready'])

    def test_webhook_rejects_bad_signature(self):
        status, _, _ = self.post_webhook(SAMPLE, sign(SAMPLE, 'wrong'))
        self.assertEqual(status, 401)

    def test_webhook_ignores_other_event_types(self):
        raw = json.dumps({'type': 'post_call_audio', 'data': {}}).encode()
        self.assertEqual(self.post_webhook(raw)[1], 'Ignored')

    def test_webhook_rejects_bad_conversation_id(self):
        event = json.loads(SAMPLE)
        event['data']['conversation_id'] = '../etc'
        self.assertEqual(self.post_webhook(json.dumps(event).encode())[0], 400)

    def test_full_flow_save_view_delete(self):
        event = json.loads(SAMPLE)
        event['data']['conversation_id'] = 'conv_flow_test'
        raw = json.dumps(event).encode()
        self.assertEqual(self.post_webhook(raw)[:2], (200, 'Report saved'))
        self.assertEqual(self.post_webhook(raw)[0], 200)  # duplicate delivery is harmless

        status, body, _ = self.request('/')
        self.assertEqual(status, 200)
        self.assertEqual(body.count('/reports/conv_flow_test'), 1)
        self.assertIn('Experienced picker', body)

        status, body, _ = self.request('/reports/conv_flow_test')
        self.assertEqual(status, 200)
        self.assertIn('Marcus Delgado', body)

        bad = urllib.parse.urlencode({'token': 'nope'}).encode()
        self.assertEqual(self.request('/reports/conv_flow_test/delete', bad)[0], 403)

        good = urllib.parse.urlencode({'token': bridge.delete_token('conv_flow_test')}).encode()
        status, _, headers = self.request('/reports/conv_flow_test/delete', good)
        self.assertEqual((status, headers['Location']), (303, '/'))
        self.assertEqual(self.request('/reports/conv_flow_test')[0], 404)

    def test_reports_require_password(self):
        self.assertEqual(self.request('/', auth=None)[0], 401)
        self.assertEqual(self.request('/', auth='wrong password!')[0], 401)

    def test_lockout_after_repeated_failures(self):
        for _ in range(bridge.MAX_FAILURES):
            self.request('/', auth='wrong password!', client='10.9.9.9')
        self.assertEqual(self.request('/', client='10.9.9.9')[0], 429)
        self.assertEqual(self.request('/', client='10.1.1.1')[0], 200)


if __name__ == '__main__':
    unittest.main()
