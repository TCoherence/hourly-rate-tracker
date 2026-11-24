"""Collector logs expose status changes without running a real VPN command."""

import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import Application, COLLECTOR_LOG, _parse_log_timestamp
import vpn


class CollectorLoggingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        platform = patch.object(vpn.sys, "platform", "darwin")
        platform.start()
        self.addCleanup(platform.stop)
        self.payload = "connected"

        def detector(settings):
            return vpn.detect(settings, runner=lambda args: self.payload)

        self.app = Application(self.directory.name, detector=detector)
        self.addCleanup(self.app.close)
        self.app.store.save_settings({"provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})

    def test_log_timestamps_support_compact_iso_and_utc_offsets(self):
        cases = (
            ("2037-01-02T03:04:05-0800", "2037-01-02T03:04:05-08:00"),
            ("2037-01-02T03:04:05+0530", "2037-01-02T03:04:05+05:30"),
            ("2037-01-02T03:04:05+05:30", "2037-01-02T03:04:05+05:30"),
            ("2037-01-02T03:04:05Z", "2037-01-02T03:04:05+00:00"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(_parse_log_timestamp(value).isoformat(), expected)
        with self.assertRaises(ValueError):
            _parse_log_timestamp("not-a-date")

    def test_initial_observation_and_raw_status_changes_log_once(self):
        with self.assertLogs(COLLECTOR_LOG, level="INFO") as captured:
            for state in ("connected", "connected", "disconnected", "disconnected",
                          "reconnecting", "reconnecting", "connected", "connected"):
                self.payload = state
                self.app.sample()
        events = [json.loads(record.getMessage()) for record in captured.records]
        self.assertEqual(len(events), 4)
        self.assertEqual([event["state"] for event in events],
                         ["connected", "disconnected", "unknown", "connected"])
        self.assertIn("断开", events[1]["message"])
        self.assertNotIn("reconnecting", events[2]["message"])
        self.assertTrue(all(event["provider"] == "script" for event in events))
        self.assertTrue(all(event["event"] == "vpn_status" for event in events))

    def test_log_contains_only_status_and_escapes_embedded_newlines(self):
        original_status = "disconnected\nFAKE_LOG_ENTRY"
        self.payload = original_status + "\nPRIVATE_DIAGNOSTIC"
        self.app.store.save_settings({"annual_salary": 123456})
        with self.assertLogs(COLLECTOR_LOG, level="INFO") as captured:
            self.app.sample()
        text = captured.records[0].getMessage()
        event = json.loads(text)
        self.assertEqual(set(event), {"event", "provider", "state", "message"})
        self.assertNotIn(original_status, event["message"])
        self.assertEqual(len(text.splitlines()), 1)
        for private in ("PRIVATE_NODE", "PRIVATE_SPEED", "PRIVATE_DIAGNOSTIC", "123456",
                        self.app.token, self.app.session_token):
            self.assertNotIn(private, text)

    def test_sampling_failures_log_unknown_once_and_then_recovery(self):
        self.app.sample()
        for target in ("settings", "record", "detector"):
            with self.subTest(target=target):
                owner = self.app if target == "detector" else self.app.store
                with self.assertLogs(COLLECTOR_LOG, level="INFO") as captured:
                    with patch.object(owner, target, side_effect=OSError("PRIVATE_FAILURE")) as failing:
                        self.app.safe_sample()
                        self.app.safe_sample()
                        # A failed settings read must not be retried by the logging path.
                        self.assertEqual(failing.call_count, 2)
                    self.app.safe_sample()
                events = [json.loads(record.getMessage()) for record in captured.records]
                self.assertEqual([event["state"] for event in events], ["unknown", "connected"])
                self.assertNotIn("PRIVATE_FAILURE", "\n".join(captured.output))

    def test_read_only_status_check_does_not_log_or_consume_initial_event(self):
        before = self.app.store.sync_status()
        with patch.object(COLLECTOR_LOG, "info") as log:
            self.assertEqual(self.app.check_script()["state"], "connected")
            log.assert_not_called()
            self.assertIsNone(self.app.last_checked)
            self.assertEqual(self.app.store.sync_status(), before)
            self.app.sample()
            log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
