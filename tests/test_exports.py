"""Exports contain local data, require authentication, and never modify the store."""
import csv
from datetime import datetime
import http.client
import io
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import Application, LocalServer, handler_for

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2037, 11, 14, 12, tzinfo=ZONE).timestamp()


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.app = Application(self.temp.name, detector=lambda _: ("disabled", "test"))
        self.app.store.save_settings({"annual_salary": 208800, "timezone": str(ZONE)})
        start = datetime(2037, 11, 13, 9, tzinfo=ZONE).timestamp()
        for sec in range(0, 3601, 30):
            self.app.store.record(start + sec, "connected")
        self.app.store.sync(NOW)
        self.app.store.record(start + 3605, "unknown")  # pending in JSON, not CSV
        self.app.store.save_manual_entries([{"date": "2037-11-13", "kind": "intervals",
                                             "intervals": [{"start": "11:00", "end": "12:00"}],
                                             "note": "=HYPERLINK(unsafe)"}], now=NOW)
        self.app.store.save_manual_entries([{"date": "2037-11-13", "kind": "intervals_override",
                                             "intervals": [{"start": "09:00", "end": "12:00"}]}], now=NOW)
        self.server = LocalServer(("127.0.0.1", 0), handler_for(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.clock = patch("app.time.time", return_value=NOW)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.temp.cleanup()

    def get(self, path, authenticated=True):
        port = self.server.server_address[1]
        headers = {"Host": f"127.0.0.1:{port}"}
        if authenticated:
            headers["X-Session-Token"] = self.app.session_token
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def post(self, path, value, authenticated=True, csrf=True):
        port = self.server.server_address[1]
        headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
        if authenticated:
            headers["X-Session-Token"] = self.app.session_token
        if csrf:
            headers["X-CSRF-Token"] = self.app.token
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("POST", path, body=json.dumps(value), headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_backup_is_authenticated_complete_and_read_only(self):
        before = self.app.store.export_snapshot()
        self.assertEqual(self.get("/api/export?format=json", False)[0], 401)
        self.assertEqual(self.get("/api/export?format=xml")[0], 400)
        status, headers, body = self.get("/api/export?format=json")
        self.assertEqual(status, 200)
        self.assertIn('attachment;', headers["Content-Disposition"])
        result = json.loads(body)
        self.assertEqual(result["format"], "hourly-rate-backup")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["observations"], before["observations"])
        self.assertEqual(result["settings"], before["settings"])
        self.assertEqual(result["manual_override_backups"], before["manual_override_backups"])
        self.assertEqual(len(result["manual_override_backups"]), 1)
        self.assertGreater(result["observations"][-1]["id"], result["metadata"]["published_seq"])
        self.assertNotIn(self.app.session_token, body.decode())
        self.assertNotIn(self.app.token, body.decode())
        self.assertEqual(self.app.store.export_snapshot(), before)

    def test_csv_matches_dashboard_and_excludes_private_note(self):
        expected = next(d for d in self.app.dashboard("month")["summary"]["days"] if d["date"] == "2037-11-13")
        status, headers, body = self.get("/api/export?format=csv")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/csv"))
        self.assertNotIn(b"HYPERLINK", body)
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
        d = next(d for d in rows if d["date"] == "2037-11-13")
        self.assertEqual(float(d["work_hours"]), expected["work_hours"])
        self.assertEqual(float(d["vpn_hours"]), expected["vpn_work_hours"])
        self.assertEqual(d["manual_kind"], "intervals_override")

    def test_restore_requires_auth_and_csrf_and_preserves_rollback(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        # Some current data exists after the backup; it must be retained in a
        # private rollback file even though restoring intentionally replaces it.
        self.app.store.record(NOW - 60, "connected")
        self.app.store.save_settings({"provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})
        before = self.app.store.export_snapshot()
        self.assertEqual(self.post("/api/restore", {"backup": backup}, authenticated=False)[0], 403)
        self.assertEqual(self.post("/api/restore", {"backup": backup}, csrf=False)[0], 403)
        status, result = self.post("/api/restore", {"backup": backup})
        self.assertEqual(status, 200)
        self.assertFalse(result["tracking_enabled"])
        rollback = Path(result["rollback_path"])
        self.assertEqual(os.stat(rollback).st_mode & 0o777, 0o600)
        saved = json.loads(rollback.read_text())
        self.assertEqual(saved["observations"], before["observations"])
        self.assertEqual(saved["settings"], before["settings"])
        restored = self.app.store.export_snapshot()
        self.assertEqual(restored["observations"], backup["observations"])
        self.assertEqual(restored["manual_entries"], backup["manual_entries"])
        self.assertEqual(restored["manual_override_backups"], backup["manual_override_backups"])
        self.assertFalse(restored["settings"]["tracking_enabled"])
        self.assertEqual(self.app.state, "disabled")
        self.app.store.delete_manual_entry("2037-11-13")
        self.assertEqual(self.app.store.manual_entries()[0]["kind"], "intervals")

    def test_invalid_restore_and_database_error_do_not_lose_data(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        before = self.app.store.export_snapshot()
        backup["version"] = 999
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 400)
        self.assertEqual(self.app.store.export_snapshot(), before)
        self.assertFalse(list(self.app.store.path.glob("before-restore-*.json")))
        backup["version"] = 1
        # Simulate a write failure after DELETE; the transaction rolls back.
        self.app.store.db.execute("CREATE TRIGGER fail_restore BEFORE INSERT ON observations BEGIN SELECT RAISE(ABORT, 'test'); END")
        self.app.store.db.commit()
        status, _ = self.post("/api/restore", {"backup": backup})
        self.assertEqual(status, 500)
        self.assertEqual(self.app.store.export_snapshot(), before)
        self.assertEqual(len(list(self.app.store.path.glob("before-restore-*.json"))), 1)

    def test_extreme_timestamps_and_out_of_day_cutoff_are_rejected(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        before = self.app.store.export_snapshot()
        backup["observations"][0]["ts"] = 1e100
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 400)
        backup["observations"][0]["ts"] = before["observations"][0]["ts"]
        backup["manual_entries"][0]["edit_cutoff"] = int(NOW)
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 400)
        self.assertEqual(self.app.store.export_snapshot(), before)
        self.assertFalse(list(self.app.store.path.glob("before-restore-*.json")))

    def test_duplicate_sleep_start_is_rejected_before_any_write(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        sleep = {"start": NOW - 60, "end": NOW - 30, "state": "connected",
                 "last_sample_ts": NOW - 65, "abandoned": True}
        backup["sleep_intervals"] = [sleep, dict(sleep)]
        before = self.app.store.export_snapshot()
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 400)
        self.assertEqual(self.app.store.export_snapshot(), before)
        self.assertFalse(list(self.app.store.path.glob("before-restore-*.json")))

    def test_empty_today_override_round_trips(self):
        revision = self.app.store.manual_revision("2037-11-14")
        self.app.store.save_manual_entries([{"date": "2037-11-14", "kind": "intervals_override", "intervals": [],
                                             "edit_cutoff": int(NOW), "edit_revision": revision}], now=NOW)
        backup = json.loads(self.get("/api/export?format=json")[2])
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 200)
        self.assertEqual(self.app.store.manual_entries()[-1]["intervals"], [])

    def test_restore_rejects_duplicate_json_keys(self):
        port = self.server.server_address[1]
        headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json",
                   "X-Session-Token": self.app.session_token, "X-CSRF-Token": self.app.token}
        before = self.app.store.export_snapshot()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", "/api/restore", body='{"backup":{"version":1,"version":2}}', headers=headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn("重复字段", json.loads(response.read())["error"])
        finally:
            conn.close()
        self.assertEqual(self.app.store.export_snapshot(), before)

    def test_cutoff_local_remains_valid_after_timezone_change(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        backup["manual_entries"][0]["edit_cutoff"] = int(NOW)
        backup["manual_entries"][0]["edit_cutoff_local"] = "12:00"
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 200)
        self.assertEqual(self.app.store.manual_entries()[0]["edit_cutoff_local"], "12:00")

    def test_restore_does_not_import_verification_and_abandons_open_sleep(self):
        self.app.store.save_settings({"provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})
        self.app.store.begin_sleep(NOW - 10, "connected", NOW - 15)
        backup = json.loads(self.get("/api/export?format=json")[2])
        backup["metadata"]["verification:example"] = ["connected", "disconnected"]
        status, _ = self.post("/api/restore", {"backup": backup})
        self.assertEqual(status, 200)
        current = self.app.store.export_snapshot()
        self.assertFalse(current["settings"]["tracking_enabled"])
        self.assertTrue(current["sleep_intervals"][0]["abandoned"])
        self.assertFalse(any(key.startswith("verification:") for key in current["metadata"]))

    def test_oversize_backup_does_not_export_or_restore_without_rollback(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        before = self.app.store.export_snapshot()
        with patch("exporting.MAX_BACKUP_BYTES", 10):
            status, _, body = self.get("/api/export?format=json")
            self.assertEqual(status, 413)
            self.assertIn("备份上限", json.loads(body)["error"])
            status, result = self.post("/api/restore", {"backup": backup})
            self.assertEqual(status, 400)
            self.assertIn("备份上限", result["error"])
        self.assertEqual(self.app.store.export_snapshot(), before)
        self.assertFalse(list(self.app.store.path.glob("before-restore-*.json")))

    def test_restore_json_rebuilds_sequence_and_rejects_near_exhausted_ids(self):
        backup = json.loads(self.get("/api/export?format=json")[2])
        expected = backup["observations"][-1]["id"]
        self.app.store.db.execute("UPDATE sqlite_sequence SET seq=9223372036854775807 WHERE name='observations'")
        self.app.store.db.commit()
        status, _ = self.post("/api/restore", {"backup": backup})
        self.assertEqual(status, 200)
        self.app.store.record(NOW + 1, "connected")
        self.app.store.record(NOW + 2, "disconnected")
        self.assertEqual([x["id"] for x in self.app.store.export_snapshot()["observations"]][-2:], [expected + 1, expected + 2])
        before = self.app.store.export_snapshot()
        backup["observations"][-1]["id"] = 2**62
        self.assertEqual(self.post("/api/restore", {"backup": backup})[0], 400)
        self.assertEqual(self.app.store.export_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
