"""Persistent browser grant isolation, expiry, revocation and security checks."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Application, LocalServer, handler_for
from browser_auth import BrowserGrants, LIFETIME


class GrantStorageTests(unittest.TestCase):
    def test_grants_expire_and_are_saved_only_as_hashes(self):
        with tempfile.TemporaryDirectory() as directory, patch('browser_auth.time.time', return_value=1_000_000):
            grants = BrowserGrants(directory)
            token, expires = grants.issue()
            other, _ = grants.issue()
            self.assertNotEqual(token, other)
            self.assertEqual(expires, 1_000_000 + LIFETIME)
            self.assertTrue(grants.verify(token))
            raw = grants.path.read_text()
            self.assertNotIn(token, raw)
            self.assertIn(hashlib.sha256(token.encode()).hexdigest(), raw)
            self.assertEqual(os.stat(grants.path).st_mode & 0o777, 0o600)
            self.assertTrue(BrowserGrants(directory).verify(token))
            with patch('browser_auth.time.time', return_value=expires):
                self.assertFalse(grants.verify(token))

    def test_invalid_registry_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            grants = BrowserGrants(directory)
            token, _ = grants.issue()
            grants.path.write_text('invalid')
            self.assertFalse(grants.verify(token))
            with self.assertRaises(ValueError):
                grants.issue()
            grants.path.unlink()
            other = Path(directory) / 'unrelated'
            other.write_text('unchanged')
            grants.path.symlink_to(other)
            self.assertFalse(grants.verify(token))
            with self.assertRaises(OSError):
                grants.issue()
            self.assertEqual(other.read_text(), 'unchanged')

    def test_extend_only_the_requested_active_grant(self):
        with tempfile.TemporaryDirectory() as directory, patch('browser_auth.time.time', return_value=1_000_000):
            grants = BrowserGrants(directory)
            token, first_expiry = grants.issue()
            other, other_expiry = grants.issue()
            before = grants.path.read_text()
            self.assertIsNone(grants.extend('invalid'))
            self.assertEqual(grants.path.read_text(), before)
            with patch('browser_auth.time.time', return_value=1_000_000 + 7 * 86400):
                updated = grants.extend(token)
                self.assertEqual(updated, 1_000_000 + 7 * 86400 + LIFETIME)
                self.assertTrue(grants.verify(token))
            values = json.loads(grants.path.read_text())['grants']
            self.assertEqual(values[hashlib.sha256(other.encode()).hexdigest()], other_expiry)
            self.assertNotIn(token, grants.path.read_text())
            with patch('browser_auth.time.time', return_value=updated):
                self.assertIsNone(grants.extend(token))
            self.assertGreater(updated, first_expiry)
            self.assertEqual(os.stat(grants.path).st_mode & 0o777, 0o600)

    def test_extend_never_shortens_grant_when_clock_moves_back(self):
        with tempfile.TemporaryDirectory() as directory, patch('browser_auth.time.time', return_value=1_000_000):
            grants = BrowserGrants(directory)
            token, expiry = grants.issue()
            with patch('browser_auth.time.time', return_value=999_900):
                self.assertEqual(grants.extend(token), expiry)


class GrantHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Application(self.directory.name, detector=lambda _: ('disabled', 'test'))
        self.server = LocalServer(('127.0.0.1', 0), handler_for(self.app))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.directory.cleanup()

    def request(self, path, method='GET', headers=None, body=None):
        values = {'Host': f'127.0.0.1:{self.port}'}
        values.update(headers or {})
        if method == 'POST':
            values['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            conn.request(method, path, body=json.dumps(body or {}) if method == 'POST' else None, headers=values)
            res = conn.getresponse()
            return res.status, json.loads(res.read()), dict(res.getheaders())
        finally:
            conn.close()

    def write_headers(self):
        return {'X-Session-Token': self.app.session_token, 'X-CSRF-Token': self.app.token,
                'Origin': f'http://127.0.0.1:{self.port}', 'Sec-Fetch-Site': 'same-origin'}

    def pair(self):
        status, data, _ = self.request('/api/browser-auth/pair', 'POST', self.write_headers(), {'pair_token': self.app.pair_token})
        self.assertEqual(status, 200)
        return data['browser_token']

    def test_grant_survives_restart_without_cookie_or_startup_token(self):
        credential = self.pair()
        with patch.object(self.app, 'session_token', 'rotated'), patch.object(self.app, 'token', 'new-csrf'):
            status, body, headers = self.request('/api/session', headers={'X-Browser-Token': credential})
            self.assertEqual(status, 200)
            self.assertEqual(body['csrf_token'], 'new-csrf')
            self.assertIn('rotated', headers['Set-Cookie'])
            self.assertNotIn(credential, headers['Set-Cookie'])
            self.assertEqual(self.request('/api/session')[0], 401)
            self.assertEqual(self.request('/api/sync', 'POST', {'X-Browser-Token': credential})[0], 403)

    def test_pair_requires_authenticated_same_origin_csrf(self):
        valid = self.write_headers()
        candidates = [{}, {'X-Session-Token': self.app.session_token},
                      {**valid, 'X-CSRF-Token': 'invalid'},
                      {**valid, 'Origin': 'https://example.invalid'},
                      {**valid, 'Sec-Fetch-Site': 'cross-site'}]
        for headers in candidates:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/browser-auth/pair', 'POST', headers, {'pair_token': self.app.pair_token})[0], 403)
        self.assertFalse(self.app.browser_grants.path.exists())

    def test_pair_needs_distinct_one_time_bootstrap_token(self):
        old_pair = self.app.pair_token
        old_cookie = {'Cookie': f'hourly_session_{self.port}={self.app.session_token}',
                      'X-CSRF-Token': self.app.token, 'Origin': f'http://127.0.0.1:{self.port}'}
        self.assertEqual(self.request('/api/browser-auth/pair', 'POST', old_cookie, {'pair_token': 'wrong'})[0], 403)
        self.pair()
        self.assertNotEqual(old_pair, self.app.pair_token)
        self.assertEqual(self.request('/api/browser-auth/pair', 'POST', self.write_headers(), {'pair_token': old_pair})[0], 403)

    def test_revoke_invalidates_persistent_and_short_credentials(self):
        token1, token2 = self.pair(), self.pair()
        old_session, old_csrf, old_pair = self.app.session_token, self.app.token, self.app.pair_token
        status, _, _ = self.request('/api/browser-auth/revoke-all', 'POST', self.write_headers())
        self.assertEqual(status, 200)
        for token in (token1, token2):
            self.assertEqual(self.request('/api/session', headers={'X-Browser-Token': token})[0], 401)
        self.assertEqual(self.request('/api/session', headers={'X-Session-Token': old_session})[0], 401)
        self.assertEqual(self.request('/api/session', headers={'Cookie': f'hourly_session_{self.port}={old_session}'})[0], 401)
        self.assertNotEqual(self.app.token, old_csrf)
        self.assertNotEqual(self.app.pair_token, old_pair)
        access = json.loads((Path(self.directory.name) / 'access.json').read_text())
        self.assertEqual(access['session_token'], self.app.session_token)
        self.assertEqual(access['port'], self.port)
        self.assertEqual(access['pair_token'], self.app.pair_token)
        self.assertEqual(self.request('/api/session', headers={'X-Session-Token': access['session_token']})[0], 200)

    def test_revoke_requires_valid_csrf_and_origin(self):
        credential = self.pair()
        for headers in ({'X-Browser-Token': credential}, {**self.write_headers(), 'Origin': 'https://evil.invalid'}):
            self.assertEqual(self.request('/api/browser-auth/revoke-all', 'POST', headers)[0], 403)
        self.assertEqual(self.request('/api/session', headers={'X-Browser-Token': credential})[0], 200)

    def test_extend_uses_only_current_browser_and_keeps_token_valid(self):
        token, other = self.pair(), self.pair()
        key = hashlib.sha256(other.encode()).hexdigest()
        other_expiry = self.app.browser_grants._read()[key]
        headers = {'X-Browser-Token': token, 'X-CSRF-Token': self.app.token,
                   'Origin': f'http://127.0.0.1:{self.port}', 'Sec-Fetch-Site': 'same-origin'}
        status, body, _ = self.request('/api/browser-auth/extend', 'POST', headers)
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {'expires_at'})
        self.assertTrue(self.app.browser_grants.verify(token))
        self.assertEqual(self.app.browser_grants._read()[key], other_expiry)
        self.assertEqual(self.request('/api/session', headers={'X-Browser-Token': token})[0], 200)

    def test_extend_requires_active_browser_grant_csrf_and_origin(self):
        token = self.pair()
        valid = {**self.write_headers(), 'X-Browser-Token': token}
        invalid = [self.write_headers(), {**valid, 'X-Browser-Token': 'wrong'},
                   {**valid, 'X-CSRF-Token': 'wrong'}, {**valid, 'Origin': 'https://evil.invalid'},
                   {**valid, 'Sec-Fetch-Site': 'cross-site'}]
        for headers in invalid:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/browser-auth/extend', 'POST', headers)[0], 403)
        self.assertEqual(self.request('/api/browser-auth/extend', 'POST', valid, {'other': 'value'})[0], 400)
        with patch('browser_auth.time.time', return_value=self.app.browser_grants._read()[hashlib.sha256(token.encode()).hexdigest()]):
            self.assertEqual(self.request('/api/browser-auth/extend', 'POST', valid)[0], 403)
        self.app.browser_grants.clear()
        self.assertEqual(self.request('/api/browser-auth/extend', 'POST', valid)[0], 403)


if __name__ == '__main__':
    unittest.main()
