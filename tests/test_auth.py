"""Browser-session auth checks using temporary storage and loopback only."""

import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import Application, LocalServer, handler_for


class BrowserSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Application(self.directory.name, detector=lambda _: ("disabled", "test"))
        self.server = LocalServer(("127.0.0.1", 0), handler_for(self.app))
        self.port = self.server.server_address[1]
        self.cookie_name = f"hourly_session_{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.directory.cleanup()

    def request(self, path="/api/session", method="GET", headers=None, body=None):
        request_headers = {"Host": f"127.0.0.1:{self.port}"}
        if method == "POST":
            request_headers["Content-Type"] = "application/json"
            if body is None: body = "{}"
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            payload = response.read()
            return response.status, json.loads(payload), dict(response.getheaders())
        finally:
            connection.close()

    def cookie_header(self, token=None):
        return {"Cookie": f"{self.cookie_name}={token or self.app.session_token}"}

    def test_authorized_launch_establishes_private_browser_session(self):
        status, data, headers = self.request(headers={"X-Session-Token": self.app.session_token})
        self.assertEqual(status, 200)
        self.assertEqual(data, {"csrf_token": self.app.token})
        cookies = SimpleCookie(headers["Set-Cookie"])
        cookie = cookies[self.cookie_name]
        self.assertEqual(cookie.value, self.app.session_token)
        self.assertEqual(cookie["path"], "/")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertFalse(cookie["domain"])
        self.assertFalse(cookie["secure"])
        self.assertFalse(cookie["expires"])
        self.assertFalse(cookie["max-age"])

        # A new tab has neither a launch fragment nor the first tab's sessionStorage.
        status, data, headers = self.request(headers={"Cookie": cookie.OutputString()})
        self.assertEqual(status, 200)
        self.assertEqual(data, {"csrf_token": self.app.token})
        self.assertNotIn("Set-Cookie", headers)

    def test_first_visit_without_credentials_stays_unauthorized(self):
        for path in ("/api/session", "/api/dashboard", "/api/status-log", "/api/autostart"):
            with self.subTest(path=path):
                status, data, headers = self.request(path)
                self.assertEqual(status, 401)
                self.assertIn("start-hourly-rate.command", data["error"])
                self.assertNotIn("Set-Cookie", headers)

    def test_invalid_malformed_and_other_port_cookies_are_rejected(self):
        values = (f"{self.cookie_name}=invalid", f'{self.cookie_name}="unterminated',
                  f"hourly_session_{self.port + 1}={self.app.session_token}")
        for value in values:
            with self.subTest(cookie=value):
                status, _, headers = self.request(headers={"Cookie": value})
                self.assertEqual(status, 401)
                self.assertNotIn("Set-Cookie", headers)

    def test_valid_cookie_can_recover_tab_with_stale_header(self):
        headers = self.cookie_header()
        headers["X-Session-Token"] = "old-session"
        self.assertEqual(self.request(headers=headers)[0], 200)

    def test_valid_header_replaces_stale_cookie(self):
        headers = self.cookie_header("old-session")
        headers["X-Session-Token"] = self.app.session_token
        status, _, response_headers = self.request(headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(SimpleCookie(response_headers["Set-Cookie"])[self.cookie_name].value,
                         self.app.session_token)

    def test_neither_invalid_credential_can_authorize(self):
        headers = self.cookie_header("invalid-cookie")
        headers["X-Session-Token"] = "invalid-header"
        self.assertEqual(self.request(headers=headers)[0], 401)
        headers["X-Session-Token"] = "non-ascii-\xe9"
        self.assertEqual(self.request(headers=headers)[0], 401)

    def test_service_restart_invalidates_cookie_and_does_not_reveal_new_token(self):
        old_credentials = self.cookie_header()
        old_credentials["X-Session-Token"] = self.app.session_token
        with patch.object(self.app, "session_token", secrets.token_urlsafe(32)):
            status, data, headers = self.request(headers=old_credentials)
            self.assertEqual(status, 401)
            self.assertNotIn(self.app.session_token, json.dumps(data))
            self.assertNotIn("Set-Cookie", headers)

    def test_health_does_not_establish_or_disclose_session(self):
        for headers in ({}, {"X-Session-Token": self.app.session_token}):
            status, data, response_headers = self.request("/api/health", headers=headers)
            self.assertEqual(status, 200)
            self.assertNotIn("csrf_token", data)
            self.assertNotIn(self.app.session_token, json.dumps(data))
            self.assertNotIn("Set-Cookie", response_headers)

    def test_cookie_authorizes_write_with_csrf_and_same_origin(self):
        headers = self.cookie_header()
        headers.update({"X-CSRF-Token": self.app.token, "Origin": f"http://127.0.0.1:{self.port}",
                        "Sec-Fetch-Site": "same-origin"})
        with patch.object(self.app, "sync") as sync:
            self.assertEqual(self.request("/api/sync", "POST", headers)[0], 200)
            sync.assert_called_once_with()

    def test_cookie_write_still_requires_csrf(self):
        for token in (None, "invalid", "non-ascii-\xe9"):
            headers = self.cookie_header()
            if token is not None:
                headers["X-CSRF-Token"] = token
            with self.subTest(csrf=token), patch.object(self.app, "sync") as sync:
                status, _, response_headers = self.request("/api/sync", "POST", headers)
                self.assertEqual(status, 403)
                self.assertNotIn("Set-Cookie", response_headers)
                sync.assert_not_called()

    def test_autostart_get_requires_session_and_post_requires_csrf(self):
        with patch('app.LoginItem') as login_item:
            self.assertEqual(self.request('/api/autostart')[0], 401)
            self.assertEqual(self.request('/api/autostart', 'POST', self.cookie_header())[0], 403)
            login_item.assert_not_called()

    def test_manual_pause_requires_session_and_csrf(self):
        with patch.object(self.app, 'set_manual_pause') as pause:
            self.assertEqual(self.request('/api/manual-pause', 'POST')[0], 403)
            self.assertEqual(self.request('/api/manual-pause', 'POST', self.cookie_header())[0], 403)
            pause.assert_not_called()

    def test_screen_alert_keep_requires_session_and_csrf(self):
        with patch.object(self.app, 'keep_screen_alert') as keep:
            self.assertEqual(self.request('/api/screen-alert/keep', 'POST')[0], 403)
            self.assertEqual(self.request('/api/screen-alert/keep', 'POST', self.cookie_header())[0], 403)
            keep.assert_not_called()

    def test_screen_alert_keep_validates_id_and_keeps_without_modifying_samples(self):
        self.app.store.save_settings({'screen_alerts':[{'id':'test-id','start':10,'end':20,'status':'pending'}]})
        before = self.app.store.export_snapshot()['observations']
        headers = self.cookie_header()
        headers['X-CSRF-Token'] = self.app.token
        status, data, _ = self.request('/api/screen-alert/keep', 'POST', headers, json.dumps({'id':'test-id'}))
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(self.app.store.settings()['screen_alerts'][0]['status'], 'kept')
        self.assertEqual(self.app.store.export_snapshot()['observations'], before)
        self.assertEqual(self.request('/api/screen-alert/keep', 'POST', headers, json.dumps({'id':'missing'}))[0], 400)

    def test_manual_pause_valid_request_and_unconfigured_error(self):
        headers = self.cookie_header()
        headers['X-CSRF-Token'] = self.app.token
        body = json.dumps({"paused":True})
        status, data, _ = self.request('/api/manual-pause', 'POST', headers, body)
        self.assertEqual(status, 400)
        self.assertIn('先在设置中启用', data['error'])
        self.app.store.save_settings({"provider":"script", "status_script_path":"/tmp/example-status", "tracking_enabled":True})
        status, data, _ = self.request('/api/manual-pause', 'POST', headers, body)
        self.assertEqual(status, 200)
        self.assertTrue(data['paused'])
        self.assertIsNone(self.app.store.settings()['manual_pauses'][-1]['end'])

    def test_cookie_write_rejects_cross_origin_cross_site_and_bad_host(self):
        rejected = ({"Origin": "https://attacker.invalid"}, {"Origin": "null"},
                    {"Sec-Fetch-Site": "cross-site"}, {"Host": "attacker.invalid"})
        for extra in rejected:
            headers = self.cookie_header()
            headers.update({"X-CSRF-Token": self.app.token, "X-Session-Token": self.app.session_token})
            headers.update(extra)
            with self.subTest(headers=extra), patch.object(self.app, "sync") as sync:
                status, _, response_headers = self.request("/api/sync", "POST", headers)
                self.assertEqual(status, 403)
                self.assertNotIn("Set-Cookie", response_headers)
                sync.assert_not_called()

    def test_cookie_get_rejects_bad_host(self):
        headers = self.cookie_header()
        headers["Host"] = "attacker.invalid"
        status, _, response_headers = self.request(headers=headers)
        self.assertEqual(status, 403)
        self.assertNotIn("Set-Cookie", response_headers)


if __name__ == "__main__":
    unittest.main()
