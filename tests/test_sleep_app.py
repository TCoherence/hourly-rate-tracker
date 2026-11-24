"""Sleep events resume collection without a browser or real power changes."""

from datetime import datetime
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Application, LocalServer, handler_for

NOW = datetime(2037, 11, 12, 22, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()


class FakePowerMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.status, self.error = "stopped", None

    def start(self):
        self.status = "running"
        return True

    def stop(self):
        self.status = "stopped"


class SleepApplicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Application(self.directory.name,
                               detector=lambda _: ("connected", "mock VPN"),
                               power_monitor_factory=FakePowerMonitor)
        self.app.store.save_settings({"tracking_enabled": True, "provider": "script", "status_script_path": "/tmp/example-status",
                                      "annual_salary": 208800})

    def tearDown(self):
        self.app.close()
        self.directory.cleanup()

    def test_native_callback_only_queues_and_records_fresh_pre_sleep_state(self):
        self.app.state, self.app.last_checked = "connected", NOW - 10
        original = self.app.store.db_path.read_bytes()
        self.app.on_power_event("sleep", NOW)
        self.assertEqual(original, self.app.store.db_path.read_bytes())
        self.app.state, self.app.last_checked = "disconnected", NOW + 3600
        self.app.on_power_event("wake", NOW + 3600)
        self.assertTrue(self.app.process_power_events())
        interval = self.app.store.sleep_intervals()[0]
        self.assertEqual((interval["start"], interval["end"], interval["state"], interval["last_sample_ts"]),
                         (NOW, NOW + 3600, "connected", NOW - 10))
        self.assertFalse(self.app.system_sleeping)

    def test_toggle_recalculates_same_minute_without_touching_observations_or_demo(self):
        self.app.store.save_settings({"pause_on_sleep": True})
        self.app.store.record(NOW - 3600, "connected")
        self.app.store.record(NOW, "connected")
        self.app.store.sync(NOW)
        self.app.store.begin_sleep(NOW - 3600, "connected", NOW - 3600)
        self.app.store.end_sleep(NOW)
        original = self.app.store.published_samples()
        with patch("app.time.time", return_value=NOW):
            paused = self.app.dashboard("today")["summary"]
            demo = self.app.dashboard("today", demo=True)["summary"]
            self.assertEqual(paused["work_hours"], 0)
            self.app.settings({"pause_on_sleep": False})
            counted = self.app.dashboard("today")["summary"]
            self.assertEqual(counted["work_hours"], 1)
            self.assertEqual(counted["sleep_estimated_hours"], 1)
            self.assertEqual(self.app.dashboard("today", demo=True)["summary"], demo)
            self.app.settings({"pause_on_sleep": True})
            self.assertEqual(self.app.dashboard("today")["summary"]["work_hours"], 0)
        self.assertEqual(self.app.store.published_samples(), original)

    def test_switching_provider_during_sleep_does_not_estimate_across_settings(self):
        self.app.store.begin_sleep(NOW - 3600, "connected", NOW - 3600)
        self.app.settings({"tracking_enabled": False})
        self.app.on_power_event("wake", NOW)
        self.app.process_power_events()
        self.assertEqual(self.app.store.sleep_intervals(), [])

    def test_wake_interrupts_long_poll_wait_and_resumes_sampling_without_page(self):
        sampled, slept = threading.Event(), threading.Event()
        calls = []

        def detector(_):
            calls.append(time.time())
            sampled.set()
            return "connected", "mock VPN"

        original_begin = self.app.store.begin_sleep

        def begin(*args):
            result = original_begin(*args)
            slept.set()
            return result

        self.app.detector = detector
        self.app.store.begin_sleep(NOW, "connected", NOW)
        with patch("app.POLL_SECONDS", 3600), patch.object(self.app.store, "begin_sleep", side_effect=begin):
            self.app.start()
            self.assertTrue(sampled.wait(2))
            self.assertEqual(self.app.store.sleep_intervals(), [])  # prior process's open interval
            sampled.clear()
            self.app.on_power_event("sleep", time.time())
            self.assertTrue(slept.wait(2))
            self.assertEqual(len(calls), 1)
            self.app.on_power_event("wake", time.time())
            self.assertTrue(sampled.wait(2))
            self.assertEqual(len(calls), 2)
            self.assertFalse(self.app.system_sleeping)
            self.assertIsNotNone(self.app.store.sleep_intervals()[0]["end"])
        self.app.stop_event.set()
        self.app.collector_wake.set()
        self.app.thread.join(2)

    def test_listener_error_is_visible_but_does_not_disable_vpn_sampling(self):
        self.app.power_monitor.status = "running"
        self.app.power_monitor.error = "系统睡眠事件处理失败"
        self.app.safe_sample()
        self.assertEqual(self.app.state, "connected")
        self.assertFalse(self.app.power_status()["available"])
        self.assertIn("失败", self.app.power_status()["message"])

    def test_listener_failure_while_sleeping_does_not_leave_sampling_paused(self):
        self.app.store.begin_sleep(NOW, "connected", NOW)
        self.app.system_sleeping = True
        self.app.power_monitor.status = "unavailable"
        self.assertTrue(self.app.recover_power_monitor())
        self.assertFalse(self.app.system_sleeping)
        self.assertEqual(self.app.store.sleep_intervals(), [])
        self.app.safe_sample()
        self.assertEqual(self.app.state, "connected")
        self.assertFalse(self.app.power_status()["available"])

    def test_sleep_before_first_vpn_check_uses_unknown_not_disabled(self):
        self.app.on_power_event("sleep", NOW)
        self.app.process_power_events()
        self.assertEqual(self.app.store.sleep_intervals()[0]["state"], "unknown")

    def test_power_log_uses_event_time_and_never_exposes_extra_fields(self):
        line = {"event": "power_status", "provider": "system_power", "state": "sleep",
                "occurred_at": "2037-11-12T21:00:00-08:00", "message": "Mac 进入睡眠", "secret": "hidden"}
        (self.app.store.path / "service.log").write_text(
            "2037-11-12T22:00:00-0800 " + json.dumps(line) + "\n")
        entry = self.app.status_log()["entries"][0]
        self.assertEqual(entry["timestamp"], line["occurred_at"])
        self.assertEqual(entry["state"], "sleep")
        self.assertNotIn("secret", entry)

    def test_setting_api_persists_toggle_and_keeps_auth_and_type_checks(self):
        server = LocalServer(("127.0.0.1", 0), handler_for(self.app))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()

        def save(value, auth=True):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            headers = {"Content-Type": "application/json", "X-CSRF-Token": self.app.token}
            if auth:
                headers["X-Session-Token"] = self.app.session_token
            try:
                connection.request("POST", "/api/settings", json.dumps({"pause_on_sleep": value}), headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()
        try:
            self.assertTrue(self.app.store.settings()["pause_on_sleep"])
            self.assertEqual(save(False, auth=False)[0], 403)
            self.assertEqual(save("false")[0], 400)
            self.assertTrue(save(True)[1]["settings"]["pause_on_sleep"])
            code, body = save(False)
            self.assertEqual(code, 200)
            self.assertFalse(body["settings"]["pause_on_sleep"])
            self.assertFalse(self.app.store.settings()["pause_on_sleep"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
