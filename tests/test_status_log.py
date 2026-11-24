"""Recent status-log reads expose only bounded, validated local status events."""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import Application


def event_line(message="公司 VPN 已连接", timestamp="2037-11-12T18:44:31-0800", **fields):
    event = {"event": "vpn_status", "provider": "script",
             "state": "connected", "message": message}
    event.update(fields)
    return timestamp + " " + json.dumps(event, ensure_ascii=False) + "\n"


class StatusLogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="hourly-status-log-test-")

        def unexpected_detector(_):
            self.fail("Reading the status log must not query the real VPN")

        self.app = Application(self.directory.name, detector=unexpected_detector)
        self.path = pathlib.Path(self.directory.name) / "service.log"

    def tearDown(self):
        self.app.close()
        self.directory.cleanup()

    def test_missing_log_returns_empty_entries_without_creating_file(self):
        self.assertEqual(self.app.status_log(), {"entries": []})
        self.assertFalse(self.path.exists())

    def test_filters_unrelated_or_invalid_events_and_only_exposes_safe_fields(self):
        invalid_lines = [
            "本机仪表盘：http://127.0.0.1:8765/\n",
            "2037-11-12T18:44:31-0800 not-json\n",
            "2037-11-12T18:44:31-0800 []\n",
            event_line(event="settings_saved", annual_salary=123456),
            event_line(provider="untrusted_provider"),
            event_line(provider=["script"]),
            event_line(state="reconnecting"),
            event_line(state={"raw": "connected"}),
            event_line(message=None),
            event_line(timestamp="not-a-date"),
            event_line(timestamp="2026-02-30T18:44:31-0800"),
            event_line(timestamp="2037-11-12T18:44:31"),
            event_line(timestamp="2037-11-12"),
        ]
        safe = event_line(extra_private_field="DO_NOT_EXPOSE", annual_salary=123456)
        payload = json.loads(safe.partition(" ")[2])
        payload["timestamp"] = "1999-01-01T00:00:00+00:00"
        safe = safe.partition(" ")[0] + " " + json.dumps(payload, ensure_ascii=False) + "\n"
        self.path.write_text("".join(invalid_lines) + safe, encoding="utf-8")
        result = self.app.status_log()
        self.assertEqual(result, {"entries": [{
            "timestamp": "2037-11-12T18:44:31-08:00", "provider": "script",
            "state": "connected", "message": "公司 VPN 已连接",
        }]})
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(result))
        self.assertNotIn("annual_salary", json.dumps(result))

    def test_recognizes_supported_providers_and_states(self):
        cases = [("disabled", "disabled"), ("system", "connected"),
                 ("verified_system", "disconnected"), ("script", "unknown"),
                 ("cisco", "connected")]
        self.path.write_text("".join(event_line(provider=provider, state=state)
                                     for provider, state in cases), encoding="utf-8")
        entries = self.app.status_log()["entries"]
        self.assertEqual([(entry["provider"], entry["state"]) for entry in entries], cases)

    def test_private_legacy_aliases_keep_old_log_events_without_exposing_provider(self):
        adapters = pathlib.Path(self.directory.name) / "adapters"
        adapters.mkdir()
        (adapters / "legacy-compat.json").write_text(json.dumps({
            "version": 1,
            "providers": {
                "fictional_old_cli": {"provider": "script", "status_script_path": "local_adapter"},
                "fictional_old_native": {"provider": "verified_system"},
            },
            "environment": {},
        }))
        self.path.write_text(event_line(provider="fictional_old_cli")
                             + event_line(provider="fictional_old_native", state="disconnected")
                             + event_line(provider="untrusted_provider"), encoding="utf-8")
        entries = self.app.status_log()["entries"]
        self.assertEqual([(entry["provider"], entry["state"]) for entry in entries],
                         [("legacy_script", "connected"), ("verified_system", "disconnected")])

    def test_returns_last_30_valid_events_in_file_order(self):
        lines = []
        for index in range(45):
            lines.append(event_line(message="status " + str(index)))
            lines.append("ordinary unrelated startup message\n")
        self.path.write_text("".join(lines), encoding="utf-8")
        entries = self.app.status_log()["entries"]
        self.assertEqual(len(entries), 30)
        self.assertEqual([entry["message"] for entry in entries],
                         ["status " + str(index) for index in range(15, 45)])

    def test_tail_read_discards_cutoff_line_and_does_not_return_older_events(self):
        # The 128 KiB tail begins inside the oversized middle line; that event
        # must be discarded even though its complete JSON exists in the file.
        content = (event_line(message="older event outside the tail")
                   + event_line(message="x" * (128 * 1024))
                   + event_line(message="recent complete event"))
        self.path.write_text(content, encoding="utf-8")
        entries = self.app.status_log()["entries"]
        self.assertEqual([entry["message"] for entry in entries], ["recent complete event"])

    def test_incomplete_trailing_json_does_not_hide_previous_complete_event(self):
        self.path.write_text(event_line(message="complete event")
                             + '2037-11-12T18:44:31-0800 {"event":"vpn_status","state":',
                             encoding="utf-8")
        self.assertEqual([entry["message"] for entry in self.app.status_log()["entries"]],
                         ["complete event"])

    def test_manual_and_login_item_logs_are_combined_in_time_order(self):
        self.path.write_text(event_line(message="manual", timestamp="2037-11-12T19:44:31-0800"))
        (self.path.parent / 'autostart-service.log').write_text(
            event_line(message="login", timestamp="2037-11-12T18:44:31-0800"))
        self.assertEqual([entry['message'] for entry in self.app.status_log()['entries']], ['login', 'manual'])

    def test_message_is_bounded_and_read_does_not_change_records_or_settings(self):
        content = event_line(message="中" * 2100)
        self.path.write_text(content, encoding="utf-8")
        settings_before = self.app.store.settings()
        sync_before = self.app.store.sync_status()
        db_before = self.app.store.db_path.read_bytes()
        entries = self.app.status_log()["entries"]
        self.assertEqual(entries[0]["message"], "中" * 2000)
        self.assertEqual(self.app.store.settings(), settings_before)
        self.assertEqual(self.app.store.sync_status(), sync_before)
        self.assertEqual(self.app.store.db_path.read_bytes(), db_before)
        self.assertEqual(self.path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
