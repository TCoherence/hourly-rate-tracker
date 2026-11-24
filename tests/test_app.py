"""Integration checks for local-only storage, VPN adapters and HTTP boundaries.

No real VPN command is run. HTTP tests bind an ephemeral loopback port and inject
a detector; they never start the application's background collector.
"""

import http.client
from datetime import datetime, timezone
import json
import pathlib
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import Application, LocalServer, handler_for
from store import Store, validate_settings
import vpn


SERVICE_ID = "11111111-2222-3333-4444-555555555555"
FIXED_NOW = 1794330000.0


def fake_detector(settings):
    if not settings["tracking_enabled"]:
        return "disabled", "test collection disabled"
    return "connected", "test VPN connected"


class SettingsTests(unittest.TestCase):
    def test_theoretical_daily_hours_defaults_to_eight_and_is_validated(self):
        self.assertEqual(validate_settings({})["theoretical_daily_hours"], 8)
        for hours in (0.25, 7.5, 8, 24):
            self.assertEqual(validate_settings({"theoretical_daily_hours": hours})["theoretical_daily_hours"], hours)
        for hours in (None, True, "8", 0, -1, 24.25, float("inf"), float("nan"), 10 ** 1000):
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                validate_settings({"theoretical_daily_hours": hours})

    def test_reject_nonfinite_salaries_and_invalid_tracking_configuration(self):
        bad = [
            {"annual_salary": float("nan")},
            {"annual_salary": float("inf")},
            {"annual_salary": -float("inf")},
            {"annual_salary": True},
            {"annual_salary": "100000"},
            {"provider": "arbitrary-command"},
            {"provider": "system", "tracking_enabled": True},
            {"provider": "system", "service_id": "$(touch /tmp/unsafe)"},
            {"provider": "disabled", "tracking_enabled": True},
            {"tracking_enabled": 1},
            {"timezone": "Not/AZone"},
            {"workdays": [True]},
            {"workdays": []},
            {"upload_url": "https://external.invalid"},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings(value)

    def test_valid_system_vpn_requires_explicit_identifier(self):
        result = validate_settings({"provider": "system", "service_id": SERVICE_ID, "tracking_enabled": True})
        self.assertTrue(result["tracking_enabled"])
        self.assertEqual(result["service_id"], SERVICE_ID)
        self.assertEqual(validate_settings({"workdays": [4, 0, 0]})["workdays"], [0, 4])

    def test_cli_provider_does_not_require_system_service_identifier(self):
        settings = validate_settings({"provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})
        self.assertEqual(settings["service_id"], "")
        self.assertTrue(settings["tracking_enabled"])


class StoreTests(unittest.TestCase):
    def test_saved_project_adapter_path_moves_with_actual_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data = pathlib.Path(directory) / "custom-data"
            store = Store(data)
            try:
                saved = {**store.settings(), "provider": "script",
                         "status_script_path": vpn.LOCAL_STATUS_SCRIPT, "tracking_enabled": True}
                store._set("settings", saved)
                store.db.commit()
                self.assertEqual(store.settings()["status_script_path"], str(data.resolve() / "adapters" / "status"))
                self.assertTrue(store.settings()["tracking_enabled"])
                self.assertEqual(store._get("settings")["status_script_path"], vpn.LOCAL_STATUS_SCRIPT)
                store.save_settings({"currency": "USD"})
                self.assertEqual(store._get("settings")["status_script_path"], str(data.resolve() / "adapters" / "status"))
            finally:
                store.close()

    def test_user_chosen_script_path_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                custom = "/tmp/another-user-status-source"
                store.save_settings({"provider": "script", "status_script_path": custom,
                                     "tracking_enabled": True})
                self.assertEqual(store.settings()["status_script_path"], custom)
            finally:
                store.close()

    def test_legacy_script_settings_migrate_without_changing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            adapters = pathlib.Path(directory) / "adapters"
            adapters.mkdir()
            (adapters / "legacy-compat.json").write_text(json.dumps({
                "version": 1,
                "providers": {"old_cli": {"provider": "script", "status_script_path": "local_adapter"}},
                "environment": {},
            }))
            store = Store(directory)
            try:
                store.record(FIXED_NOW - 60, "connected")
                store.record(FIXED_NOW - 45, "disconnected")
                store.sync(FIXED_NOW)
                history = store.published_samples()
                old = {**store.settings(), "provider": "old_cli", "tracking_enabled": True}
                old.pop("status_script_path")
                store._set("settings", old)
                migrated = store.settings()
                self.assertEqual(migrated["provider"], "script")
                self.assertEqual(migrated["status_script_path"], str(pathlib.Path(directory).resolve() / "adapters" / "status"))
                self.assertTrue(migrated["tracking_enabled"])
                self.assertEqual(store._get("settings", {})["provider"], "old_cli")
                self.assertEqual(store.published_samples(), history)
                store.save_settings({"annual_salary": 100000})
            finally:
                store.close()
            store = Store(directory)
            try:
                self.assertEqual(store.settings()["provider"], "script")
                self.assertTrue(store.settings()["tracking_enabled"])
                self.assertEqual(store.published_samples(), history)
            finally:
                store.close()

    def test_daily_hours_setting_survives_restart_without_changing_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                store.record(FIXED_NOW, "connected")
                store.sync()
                store.save_settings({"theoretical_daily_hours": 7.5})
                expected = store.published_samples()
            finally:
                store.close()
            store = Store(directory)
            try:
                self.assertEqual(store.settings()["theoretical_daily_hours"], 7.5)
                self.assertEqual(store.published_samples(), expected)
            finally:
                store.close()

    def test_watermark_hides_pending_observations_and_survives_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(pathlib.Path(directory) / "data")
            try:
                self.assertFalse(store.settings()["tracking_enabled"])
                self.assertEqual(store.settings()["provider"], "disabled")
                self.assertIsNone(store.settings()["annual_salary"])
                store.record(FIXED_NOW - 30, "connected")
                store.record(FIXED_NOW - 15, "disconnected")
                self.assertEqual(store.published_samples(), [])
                self.assertEqual(store.sync_status()["pending_count"], 2)
                store.sync(FIXED_NOW)
                self.assertEqual(len(store.published_samples()), 2)
                self.assertEqual(store.sync_status()["last_synced_at"], FIXED_NOW)
                store.record(FIXED_NOW, "unknown")
                self.assertEqual(len(store.published_samples()), 2)
                self.assertEqual(store.sync_status()["pending_count"], 1)
                db_path, data_path = store.db_path, store.path
            finally:
                store.close()

            store = Store(data_path)
            try:
                self.assertEqual(len(store.published_samples()), 2)
                self.assertEqual(store.sync_status()["pending_count"], 1)
                store.sync(FIXED_NOW + 300)
                self.assertEqual(len(store.published_samples()), 3)
                self.assertEqual(store.sync_status()["pending_count"], 0)
                self.assertEqual(stat.S_IMODE(db_path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(data_path.stat().st_mode), 0o700)
            finally:
                store.close()

    def test_invalid_observation_is_never_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                for ts, state in [(float("nan"), "connected"), (FIXED_NOW, "Connecting")]:
                    with self.assertRaises(ValueError):
                        store.record(ts, state)
                self.assertEqual(store.sync_status()["pending_count"], 0)
            finally:
                store.close()


class VPNTests(unittest.TestCase):
    def test_system_parser_uses_exact_connection_state(self):
        cases = {
            "Connected\nExtended Status: secret": "connected",
            "Disconnected\n": "disconnected",
            "Connecting\n": "unknown",
            "Reconnecting\n": "unknown",
            "Disconnecting\n": "unknown",
            "VPN process is running": "unknown",
            "not Connected": "unknown",
            "": "unknown",
        }
        for output, expected in cases.items():
            with self.subTest(output=output):
                self.assertEqual(vpn.parse_system_status(output), expected)

    def test_cisco_parser_does_not_confuse_connected_and_reconnecting(self):
        cases = {
            ">> state: Connected\n": "connected",
            ">> state: Disconnected\n": "disconnected",
            ">> state: Connecting\n": "unknown",
            ">> state: Reconnecting\n": "unknown",
            ">> state: Connected\n>> state: Reconnecting\n": "unknown",
            "vpnagent is running\nConnected to service": "unknown",
            ">> notice: connected": "unknown",
            "": "unknown",
        }
        for output, expected in cases.items():
            with self.subTest(output=output):
                self.assertEqual(vpn.parse_cisco_status(output), expected)

    def test_detection_is_read_only_and_discards_raw_output(self):
        calls = []
        secret = "INTERNAL_HOSTNAME_SHOULD_NOT_BE_EXPORTED"

        def runner(args):
            calls.append(args)
            return "Connected\n" + secret

        settings = validate_settings({"provider": "system", "service_id": SERVICE_ID, "tracking_enabled": True})
        with patch.object(vpn.sys, "platform", "darwin"):
            state, message = vpn.detect(settings, runner)
        self.assertEqual(state, "connected")
        self.assertNotIn(secret, message)
        self.assertEqual(calls, [["/usr/sbin/scutil", "--nc", "status", SERVICE_ID]])

    def test_disabled_detection_does_not_execute_any_command(self):
        def fail_if_called(_):
            self.fail("Disabled collection must not execute VPN commands")

        self.assertEqual(vpn.detect(validate_settings({}), fail_if_called)[0], "disabled")

    def test_unreadable_status_becomes_unknown_without_error_output(self):
        def unavailable(_):
            raise RuntimeError("SECRET_INTERNAL_DIAGNOSTIC")

        settings = validate_settings({"provider": "system", "service_id": SERVICE_ID, "tracking_enabled": True})
        with patch.object(vpn.sys, "platform", "darwin"):
            state, message = vpn.detect(settings, unavailable)
        self.assertEqual(state, "unknown")
        self.assertNotIn("SECRET_INTERNAL_DIAGNOSTIC", message)


class VerifiedSystemTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.current_state = "connected"
        self.calls = []

        def detector(settings):
            self.calls.append(dict(settings))
            return self.current_state, "raw private diagnostic must not escape verification"

        self.app = Application(self.directory.name, detector=detector)
        self.configuration = {"provider": "verified_system", "service_id": SERVICE_ID, "tracking_enabled": True}

    def tearDown(self):
        self.app.close()
        self.directory.cleanup()

    def verify(self, expected, service_id=SERVICE_ID):
        return self.app.verify_vpn({"service_id": service_id, "expected_state": expected})

    def verify_both(self):
        self.current_state = "connected"
        self.verify("connected")
        self.current_state = "disconnected"
        return self.verify("disconnected")

    def test_unverified_or_only_one_state_cannot_enable_tracking(self):
        with self.assertRaises(ValueError):
            self.app.settings(self.configuration)
        self.assertFalse(self.app.store.settings()["tracking_enabled"])
        self.assertEqual(self.calls, [])

        first = self.verify("connected")
        self.assertFalse(first["verified"])
        self.assertEqual(first["verified_states"], ["connected"])
        self.assertEqual(self.calls[-1], {"provider": "system", "service_id": SERVICE_ID, "tracking_enabled": True})
        # Repeating the same state does not count as the required second state.
        self.assertEqual(self.verify("connected")["verified_states"], ["connected"])
        with self.assertRaises(ValueError):
            self.app.settings(self.configuration)
        self.assertFalse(self.app.store.settings()["tracking_enabled"])
        self.assertEqual(self.app.store.sync_status()["pending_count"], 0)

    def test_two_matching_states_allow_tracking_without_background_collector(self):
        verified = self.verify_both()
        self.assertTrue(verified["verified"])
        self.assertEqual(set(verified["verified_states"]), {"connected", "disconnected"})
        settings = self.app.settings(self.configuration)
        self.assertTrue(settings["tracking_enabled"])
        self.assertEqual(settings["provider"], "verified_system")
        self.assertEqual(settings["service_id"], SERVICE_ID)
        self.assertIsNone(self.app.thread)

    def test_different_uuid_cannot_reuse_verification(self):
        self.verify_both()
        other_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.assertFalse(self.app.store.verification(other_id)["verified"])
        with self.assertRaises(ValueError):
            self.app.settings({**self.configuration, "service_id": other_id})
        self.assertFalse(self.app.store.settings()["tracking_enabled"])
        self.assertTrue(self.app.store.verification(SERVICE_ID)["verified"])

    def test_mismatch_and_unknown_do_not_persist_a_passing_state(self):
        self.current_state = "unknown"
        result = self.verify("connected")
        self.assertFalse(result["verified"])
        self.assertEqual(result["verified_states"], [])
        self.current_state = "connected"
        result = self.verify("disconnected")
        self.assertEqual(result["verified_states"], [])
        self.assertNotIn("raw private diagnostic", json.dumps(result))
        self.verify("connected")
        result = self.verify("disconnected")
        self.assertFalse(result["verified"])
        self.assertEqual(result["verified_states"], [])

    def test_failed_reverification_revokes_trust_and_pauses_active_tracking(self):
        self.verify_both()
        self.app.settings(self.configuration)
        self.current_state = "connected"
        result = self.verify("disconnected")
        self.assertFalse(result["verified"])
        self.assertEqual(result["verified_states"], [])
        self.assertTrue(result["tracking_paused"])
        self.assertFalse(self.app.store.settings()["tracking_enabled"])
        self.assertEqual(self.app.store.published_samples()[-1]["state"], "unknown")
        self.assertEqual(self.app.state, "disabled")
        with self.assertRaises(ValueError):
            self.app.settings(self.configuration)
        self.verify("connected")
        with self.assertRaises(ValueError):
            self.app.settings(self.configuration)
        self.current_state = "disconnected"
        self.verify("disconnected")
        self.assertTrue(self.app.settings(self.configuration)["tracking_enabled"])

    def test_failed_reverification_stays_revoked_after_restart(self):
        self.verify_both()
        self.app.settings(self.configuration)
        self.current_state = "unknown"
        self.verify("connected")
        self.app.close()
        self.app = Application(self.directory.name, detector=fake_detector)
        self.assertFalse(self.app.store.verification(SERVICE_ID)["verified"])
        self.assertFalse(self.app.store.settings()["tracking_enabled"])
        with self.assertRaises(ValueError):
            self.app.settings(self.configuration)

    def test_other_service_failure_does_not_pause_verified_active_service(self):
        self.verify_both()
        self.app.settings(self.configuration)
        self.current_state = "unknown"
        result = self.verify("connected", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertFalse(result["tracking_paused"])
        self.assertTrue(self.app.store.settings()["tracking_enabled"])
        self.assertTrue(self.app.store.verification(SERVICE_ID)["verified"])

    def test_disconnected_samples_do_not_count_as_work(self):
        self.verify_both()
        with patch("app.time.time", return_value=FIXED_NOW - 30):
            self.app.settings(self.configuration)
        with patch("app.time.time", return_value=FIXED_NOW):
            self.app.sample()
            self.app.sync()
            result = self.app.dashboard("today")
        self.assertEqual(result["summary"]["work_hours"], 0)
        self.assertGreater(result["summary"]["observed_hours"], 0)

    def test_detector_failure_also_revokes_previous_verification(self):
        self.verify_both()
        self.app.detector = lambda _: (_ for _ in ()).throw(RuntimeError("private diagnostic"))
        result = self.verify("connected")
        self.assertFalse(result["verified"])
        self.assertEqual(result["state"], "unknown")
        self.assertNotIn("private diagnostic", json.dumps(result))

    def test_verification_persists_by_uuid_across_reopening(self):
        self.verify_both()
        self.app.close()
        self.app = Application(self.directory.name, detector=fake_detector)
        self.assertTrue(self.app.store.verification(SERVICE_ID)["verified"])
        self.assertTrue(self.app.settings(self.configuration)["tracking_enabled"])


class ScriptStatusApplicationTests(unittest.TestCase):
    def test_cli_disconnect_stops_work_and_reconnect_resumes_it(self):
        current = {"status": "connected"}
        def detector(settings):
            return vpn.detect(settings, runner=lambda args: current["status"])
        with tempfile.TemporaryDirectory() as directory, patch.object(vpn.sys, "platform", "darwin"):
            application = Application(directory, detector=detector)
            try:
                with patch("app.time.time", return_value=FIXED_NOW - 75):
                    application.settings({"provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})
                for offset, state in ((60, "disconnected"), (45, "disconnected"),
                                      (30, "connected"), (15, "connected")):
                    current["status"] = state
                    with patch("app.time.time", return_value=FIXED_NOW - offset):
                        application.sample()
                application.sync()
                with patch("app.time.time", return_value=FIXED_NOW):
                    result = application.dashboard("today")
                self.assertEqual(result["collector"]["state"], "connected")
                self.assertAlmostEqual(result["summary"]["work_hours"] * 3600, 30)
                self.assertAlmostEqual(result["summary"]["observed_hours"] * 3600, 60)
                self.assertEqual([row["state"] for row in application.store.published_samples()],
                                 ["connected", "disconnected", "disconnected", "connected", "connected"])
            finally:
                application.close()

    def test_cli_collection_preserves_unknown_boundaries_and_discards_extra_fields(self):
        current = {"status": "connected"}
        def detector(settings):
            return vpn.detect(settings, runner=lambda args: current["status"])
        with tempfile.TemporaryDirectory() as directory, patch.object(vpn.sys, "platform", "darwin"):
            application = Application(directory, detector=detector)
            try:
                with patch("app.time.time", return_value=FIXED_NOW - 60):
                    application.settings({"provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})
                self.assertEqual(application.state, "connected")
                current["status"] = "reconnecting"
                with patch("app.time.time", return_value=FIXED_NOW - 45):
                    application.sample()
                    application.sync()
                    dashboard = application.dashboard("today")
                self.assertEqual(dashboard["collector"]["state"], "unknown")
                self.assertNotIn("reconnecting", dashboard["collector"]["message"])
                self.assertNotIn("PRIVATE_NODE", json.dumps(dashboard))
                self.assertNotIn("PRIVATE_SPEED", json.dumps(dashboard))
                current["status"] = "connected"
                for stamp in (FIXED_NOW - 30, FIXED_NOW - 15):
                    with patch("app.time.time", return_value=stamp):
                        application.sample()
                application.sync()
                with patch("app.time.time", return_value=FIXED_NOW):
                    dashboard = application.dashboard("today")
                self.assertAlmostEqual(dashboard["summary"]["work_hours"] * 3600, 30)
                self.assertEqual([row["state"] for row in application.store.published_samples()],
                                 ["connected", "unknown", "connected", "connected"])
                self.assertNotIn(b"PRIVATE_NODE", application.store.db_path.read_bytes())
                self.assertNotIn(b"PRIVATE_SPEED", application.store.db_path.read_bytes())
            finally:
                application.close()

    def test_cli_can_enable_after_legacy_verification_has_been_revoked(self):
        with tempfile.TemporaryDirectory() as directory:
            application = Application(directory, detector=fake_detector)
            try:
                application.store.verify_state(SERVICE_ID, "connected")
                application.store.verify_state(SERVICE_ID, "disconnected")
                application.store.invalidate_verification(SERVICE_ID)
                configured = application.settings({"provider": "script", "status_script_path": "/tmp/example-status", "service_id": SERVICE_ID,
                                                   "tracking_enabled": True})
                self.assertTrue(configured["tracking_enabled"])
                application.store.invalidate_verification(SERVICE_ID)
                self.assertTrue(application.store.settings()["tracking_enabled"])
            finally:
                application.close()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Application(self.directory.name, detector=fake_detector)
        self.server = LocalServer(("127.0.0.1", 0), handler_for(self.app))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.directory.cleanup()

    def request(self, method, path, body=None, authenticated=True, headers=None):
        request_headers = {"Host": f"127.0.0.1:{self.port}"}
        if authenticated:
            request_headers["X-Session-Token"] = self.app.session_token
            request_headers["X-CSRF-Token"] = self.app.token
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            if not isinstance(body, (str, bytes)):
                body = json.dumps(body)
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            payload = response.read()
            return response.status, json.loads(payload), dict(response.getheaders())
        finally:
            connection.close()

    def test_private_get_needs_session_and_health_exposes_no_user_data(self):
        code, _, _ = self.request("GET", "/api/dashboard", authenticated=False)
        self.assertEqual(code, 401)
        code, data, headers = self.request("GET", "/api/dashboard")
        self.assertEqual(code, 200)
        self.assertFalse(data["privacy"]["external_upload"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        code, health, _ = self.request("GET", "/api/health", authenticated=False)
        self.assertEqual(code, 200)
        self.assertNotIn("settings", health)
        self.assertNotIn("csrf_token", health)
        self.assertNotIn("session_token", health)

    def test_wrong_host_is_rejected_even_with_valid_token(self):
        code, _, _ = self.request("GET", "/api/dashboard", headers={"Host": "attacker.invalid"})
        self.assertEqual(code, 403)

    def test_session_endpoint_requires_authentication_without_calculating_dashboard(self):
        self.assertEqual(self.request("GET", "/api/session", authenticated=False)[0], 401)
        with patch.object(self.app, "dashboard", side_effect=AssertionError("must not summarize")):
            code, data, _ = self.request("GET", "/api/session")
        self.assertEqual(code, 200)
        self.assertEqual(data, {"csrf_token": self.app.token})

    def test_cli_status_check_is_authenticated_and_does_not_start_or_write_collection(self):
        before_settings = self.app.store.settings()
        before_sync = self.app.store.sync_status()
        before_file = self.app.store.db_path.read_bytes()
        with patch.object(self.app, "detector", return_value=("unknown", '状态未知')) as detector:
            self.assertEqual(self.request("GET", "/api/script-status", authenticated=False)[0], 401)
            detector.assert_not_called()
            code, payload, _ = self.request("GET", "/api/script-status")
            self.assertEqual(code, 200)
            self.assertEqual(payload, {"state": "unknown", "message": '状态未知'})
            detector.assert_called_once_with({"provider": "script", "status_script_path": "",
                                              "tracking_enabled": True})
        self.assertEqual(self.app.store.settings(), before_settings)
        self.assertEqual(self.app.store.sync_status(), before_sync)
        self.assertEqual(self.app.store.db_path.read_bytes(), before_file)
        self.assertIsNone(self.app.last_checked)
        self.assertEqual(self.app.state, "disabled")

    def test_cli_status_check_unexpected_failure_returns_unknown_without_details(self):
        with patch.object(self.app, "detector", side_effect=RuntimeError("PRIVATE_DIAGNOSTIC")):
            code, payload, _ = self.request("GET", "/api/script-status")
        self.assertEqual(code, 200)
        self.assertEqual(payload["state"], "unknown")
        self.assertNotIn("PRIVATE_DIAGNOSTIC", json.dumps(payload))

    def test_cross_origin_post_and_missing_credentials_are_rejected(self):
        origin = {"Origin": "https://attacker.invalid"}
        code, _, _ = self.request("POST", "/api/settings", {"annual_salary": 50000}, headers=origin)
        self.assertEqual(code, 403)
        self.assertIsNone(self.app.store.settings()["annual_salary"])
        code, _, _ = self.request("POST", "/api/sync", {}, authenticated=False)
        self.assertEqual(code, 403)
        code, _, _ = self.request("POST", "/api/sync", {}, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(code, 403)

    def test_settings_and_sync_work_with_local_origin(self):
        headers = {"Origin": f"http://127.0.0.1:{self.port}"}
        code, data, _ = self.request("POST", "/api/settings", {"annual_salary": 123456}, headers=headers)
        self.assertEqual(code, 200)
        self.assertEqual(data["settings"]["annual_salary"], 123456)
        self.assertFalse(data["settings"]["tracking_enabled"])
        self.app.store.record(FIXED_NOW, "connected")
        self.assertEqual(self.app.store.sync_status()["pending_count"], 1)
        code, data, _ = self.request("POST", "/api/sync", {}, headers=headers)
        self.assertEqual(code, 200)
        self.assertFalse(data["external_upload"])
        self.assertEqual(self.app.store.sync_status()["pending_count"], 0)

    def test_invalid_settings_remain_unmodified_through_http(self):
        for body in [
            '{"annual_salary": NaN}',
            '{"annual_salary": Infinity}',
            {"provider": "system", "tracking_enabled": True},
            {"upload_url": "https://external.invalid"},
        ]:
            with self.subTest(body=body):
                code, _, _ = self.request("POST", "/api/settings", body)
                self.assertEqual(code, 400)
                self.assertIsNone(self.app.store.settings()["annual_salary"])
                self.assertFalse(self.app.store.settings()["tracking_enabled"])

    def test_salary_history_saves_and_recalculates_without_changing_observations(self):
        now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc).timestamp()
        for day in (9, 10):
            start = datetime(2026, 11, day, 9, tzinfo=timezone.utc).timestamp()
            self.app.store.record(start, "connected")
            self.app.store.record(start + 30, "disconnected")
        self.app.store.sync()
        original = self.app.store.published_samples()
        history = [{"effective_from": "2026-11-10", "annual_salary": 417600}]
        with patch("app.time.time", return_value=now):
            code, _, _ = self.request("POST", "/api/settings", {
                "annual_salary": 208800, "timezone": "UTC", "salary_history": history})
            self.assertEqual(code, 200)
            code, dashboard, _ = self.request("GET", "/api/dashboard?period=week")
            self.assertEqual(code, 200)
            self.assertEqual(dashboard["settings"]["salary_history"], history)
            self.assertAlmostEqual(dashboard["summary"]["income"], 2400)
            self.assertAlmostEqual(dashboard["summary"]["actual_rate"], 144000)
            history[0]["annual_salary"] = 626400
            self.assertEqual(self.request("POST", "/api/settings", {"salary_history": history})[0], 200)
            self.assertAlmostEqual(self.request("GET", "/api/dashboard?period=week")[1]["summary"]["actual_rate"], 192000)
            self.assertEqual(self.request("POST", "/api/settings", {"theoretical_daily_hours": 4})[0], 200)
            recalculated = self.request("GET", "/api/dashboard?period=week")[1]["summary"]
            self.assertAlmostEqual(recalculated["actual_rate"], 192000)
            self.assertAlmostEqual(recalculated["theoretical_rate"], 600)
            self.assertEqual(self.request("POST", "/api/settings", {"salary_history": history * 2})[0], 400)
            self.assertEqual(self.app.store.settings()["salary_history"], history)
        self.assertEqual(self.app.store.published_samples(), original)

    def test_path_traversal_and_invalid_period_are_rejected(self):
        for path in ["/../store.py", "/static/../../records.sqlite3", "/%2e%2e/app.py"]:
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("GET", "/api/dashboard?period=invalid")[0], 400)

    def test_raw_vpn_output_never_appears_in_dashboard_or_database(self):
        secret = "COMPANY_HOSTNAME_AND_PRIVATE_DIAGNOSTICS"
        self.app.store.save_settings({"provider": "system", "service_id": SERVICE_ID, "tracking_enabled": True})
        self.app.detector = lambda settings: vpn.detect(settings, lambda _: "Connected\n" + secret)
        with patch.object(vpn.sys, "platform", "darwin"):
            self.app.sample()
        self.app.sync()
        code, data, _ = self.request("GET", "/api/dashboard")
        self.assertEqual(code, 200)
        self.assertNotIn(secret, json.dumps(data))
        self.assertFalse(data["privacy"]["external_upload"])
        self.assertIn("127.0.0.1", data["privacy"]["sync_target"])
        self.assertNotIn(secret.encode(), self.app.store.db_path.read_bytes())

    def test_demo_never_changes_real_salary_or_records(self):
        history = [{"effective_from": "2020-01-01", "annual_salary": 54321}]
        self.app.store.save_settings({"annual_salary": 98765, "salary_history": history})
        self.app.store.record(FIXED_NOW - 30, "connected")
        self.app.store.record(FIXED_NOW, "disconnected")
        self.app.store.sync(FIXED_NOW)
        before_status = self.app.store.sync_status()
        before_rows = self.app.store.published_samples()
        with patch("app.time.time", return_value=FIXED_NOW):
            code, data, _ = self.request("GET", "/api/dashboard?demo=1&period=month")
        self.assertEqual(code, 200)
        self.assertEqual(data["mode"], "demo")
        self.assertEqual(data["demo_salary"], 180000)
        self.assertEqual(data["settings"]["annual_salary"], 98765)
        self.assertEqual(self.app.store.settings()["annual_salary"], 98765)
        self.assertEqual(self.app.store.settings()["salary_history"], history)
        self.assertEqual(data["summary"]["current_annual_salary"], 180000)
        self.assertEqual(self.app.store.sync_status(), before_status)
        self.assertEqual(self.app.store.published_samples(), before_rows)

    def test_stale_collector_is_unknown_without_extrapolated_hours(self):
        self.app.store.save_settings({"provider": "cisco", "tracking_enabled": True})
        self.app.state = "connected"
        self.app.last_checked = FIXED_NOW - 46
        self.app.store.record(FIXED_NOW - 46, "connected")
        self.app.sync()
        with patch("app.time.time", return_value=FIXED_NOW):
            data = self.app.dashboard("today")
        self.assertEqual(data["collector"]["state"], "unknown")
        self.assertEqual(data["summary"]["work_hours"], 0)

    def test_vpn_verification_requires_both_tokens_and_local_origin(self):
        calls = []

        def detector(settings):
            calls.append(settings)
            return "connected", "test state"

        self.app.detector = detector
        body = {"service_id": SERVICE_ID, "expected_state": "connected"}
        cases = [
            {"authenticated": False},
            {"headers": {"X-Session-Token": "wrong"}},
            {"headers": {"X-CSRF-Token": "wrong"}},
            {"headers": {"Origin": "https://attacker.invalid"}},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(self.request("POST", "/api/verify-vpn", body, **arguments)[0], 403)
        self.assertEqual(calls, [])
        self.assertEqual(self.app.store.verification(SERVICE_ID)["verified_states"], [])
        code, result, _ = self.request("POST", "/api/verify-vpn", body,
                                       headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(code, 200)
        self.assertEqual(result["verified_states"], ["connected"])
        self.assertFalse(result["verified"])
        self.assertEqual(len(calls), 1)

    def test_invalid_vpn_verification_payload_cannot_mark_success(self):
        for body in [
            {"service_id": "not-a-uuid", "expected_state": "connected"},
            {"service_id": SERVICE_ID, "expected_state": "reconnecting"},
            {"service_id": SERVICE_ID, "expected_state": True},
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/verify-vpn", body)[0], 400)
        self.assertEqual(self.app.store.verification(SERVICE_ID)["verified_states"], [])


if __name__ == "__main__":
    unittest.main()
