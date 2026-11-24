"""Manual pause keeps VPN evidence while excluding paused automatic work."""
from datetime import date, datetime, timezone
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import Application
from core import summarize, calendar_month, history_day
from exporting import json_backup, validate_backup
from binary_backup import snapshot_file, restore_sqlite_file

DAY = date(2038, 4, 12)
START = datetime(2038, 4, 12, 9, tzinfo=timezone.utc).timestamp()


def observations(seconds=3600):
    return [{"ts": START + t, "state": "connected"} for t in range(0, seconds + 1, 15)]


class ManualPauseTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = Application(self.tmp.name, detector=lambda _: ("connected", "test"))
        self.app.store.save_settings({"timezone": "UTC", "provider": "script", "status_script_path": "/tmp/example-status", "tracking_enabled": True})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_pause_overlay_consistent_and_manual_override_wins(self):
        settings = self.app.store.settings()
        settings["manual_pauses"] = [{"start": START + 900, "end": START + 2700}]
        rows = observations()
        summary = summarize(rows, settings, "today", START + 3600)
        self.assertAlmostEqual(summary["work_hours"], 0.5)
        self.assertAlmostEqual(summary["period_days"][0]["vpn_work_hours"], 1)
        self.assertTrue(any(item["source"] == "manual_paused" for item in summary["timeline"]))
        month = calendar_month(rows, settings, date(2038, 4, 1), START + 3600)
        self.assertAlmostEqual(next(d for d in month if d["date"] == DAY.isoformat())["work_hours"], 0.5)
        day = history_day(rows, settings, DAY, START + 3600)
        self.assertTrue(any(item["source"] == "manual_paused" for item in day["segments"]))
        manual = [{"date": DAY.isoformat(), "kind": "intervals", "intervals": [{"start":"09:20", "end":"09:40"}], "note":""}]
        self.assertAlmostEqual(summarize(rows, settings, "today", START + 3600, manual_entries=manual)["work_hours"], 5/6)

    def test_pause_covers_sleep_estimate_and_night_rule(self):
        settings = self.app.store.settings()
        settings.update({"pause_on_sleep": False, "manual_pauses": [{"start": START + 300, "end": START + 900}]})
        rows = observations(1200)
        sleeps = [{"start": START + 300, "end": START + 900, "state":"connected", "last_sample_ts":START + 285, "abandoned":False}]
        result = summarize(rows, settings, "today", START + 1200, sleep_intervals=sleeps)
        self.assertAlmostEqual(result["work_hours"], 600 / 3600)
        self.assertEqual(result["sleep_estimated_hours"], 0)
        sleep_only = summarize([], settings, "today", START + 1200, sleep_intervals=sleeps)
        self.assertEqual(sleep_only["period_days"][0]["observed_hours"], 0)
        self.assertEqual(sleep_only["period_days"][0]["income"], 0)
        self.assertTrue(any(x["state"] == "unknown" and x["source"] == "manual_paused" for x in sleep_only["timeline"]))

    def test_paused_known_connection_remains_recorded_and_disconnected_is_preserved(self):
        settings = self.app.store.settings()
        settings.update({"annual_salary":260000, "manual_pauses": [{"start":START,"end":START + 3600}]})
        rows = observations()
        result = summarize(rows, settings, "today", START + 3600)
        day = result["period_days"][0]
        self.assertEqual(day["work_hours"], 0)
        self.assertGreater(day["observed_hours"], 0)
        self.assertGreater(day["income"], 0)
        self.assertTrue(any(x["state"] == "paused" and x["source"] == "manual_paused" for x in result["timeline"]))
        disconnected = [{**row, "state":"disconnected"} for row in rows]
        other = summarize(disconnected, settings, "today", START + 3600)
        self.assertGreater(other["period_days"][0]["observed_hours"], 0)
        self.assertTrue(any(x["state"] == "disconnected" for x in other["timeline"]))
        unknown = [{**row, "state":"unknown"} for row in rows]
        self.assertEqual(summarize(unknown, settings, "today", START + 3600)["period_days"][0]["observed_hours"], 0)

    def test_pause_resume_restart_and_live_lock(self):
        with patch("app.time.time", return_value=START):
            self.app.sample()
        with patch("app.time.time", return_value=START + 15):
            self.assertEqual(self.app.set_manual_pause(True), {"paused": True})
        self.assertIsNone(self.app.active_tracking(START + 15, self.app.store.settings()))
        count = len(self.app.store.export_snapshot()["observations"])
        with patch("app.time.time", return_value=START + 30):
            self.assertEqual(self.app.set_manual_pause(True), {"paused": True})
        self.assertEqual(count, len(self.app.store.export_snapshot()["observations"]))
        # A reopened app reads the persisted pause without assuming VPN is disconnected.
        reopened = Application(self.tmp.name, detector=lambda _: ("connected", "test"))
        try:
            self.assertIsNone(reopened.store.settings()["manual_pauses"][-1]["end"])
        finally:
            reopened.store.close()
        with patch("app.time.time", return_value=START + 45):
            self.assertEqual(self.app.set_manual_pause(False), {"paused": False})
        settings = self.app.store.settings()
        self.assertEqual(settings["manual_pauses"], [{"start": START + 15, "end": START + 45}])
        self.assertGreaterEqual(datetime.fromisoformat(self.app.active_tracking(START + 45, settings)["start"]).timestamp(), START + 45)

    def test_old_and_new_json_and_sqlite_backups(self):
        old = self.app.store.export_snapshot()
        del old["settings"]["manual_pauses"]
        self.assertEqual(validate_backup(json_backup(old, START))["settings"]["manual_pauses"], [])
        self.app.store.save_settings({"manual_pauses": [{"start": START, "end": None}]})
        payload = json_backup(self.app.store.export_snapshot(), START + 1)
        self.assertEqual(validate_backup(payload)["settings"]["manual_pauses"], [{"start":START,"end":None}])
        path = snapshot_file(self.app.store)
        try:
            self.app.store.save_settings({"manual_pauses": []})
            restore_sqlite_file(self.app, path)
            self.assertEqual(self.app.store.settings()["manual_pauses"], [{"start":START,"end":None}])
            self.assertFalse(self.app.store.settings()["tracking_enabled"])
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_and_unconfigured_pause_rejected(self):
        with self.assertRaises(ValueError): self.app.settings({"manual_pauses": []})
        with self.assertRaises(ValueError): self.app.store.save_settings({"manual_pauses": [{"start":10,"end":9}]})
        self.app.store.save_settings({"tracking_enabled":False})
        with self.assertRaises(ValueError): self.app.set_manual_pause(True)

    def test_resume_lock_uses_minute_precision_conservatively(self):
        self.app.store.save_settings({"manual_pauses": [{"start": START + 1, "end": START + 47}]})
        with patch("app.time.time", return_value=START + 48):
            self.app.sample()
        active = self.app.active_tracking(START + 48, self.app.store.settings())
        self.assertEqual(datetime.fromisoformat(active["start"]).timestamp(), START + 48)
        self.assertEqual(datetime.fromisoformat(active["locked_from"]).timestamp(), START)
        self.app.store.sync(START + 48)
        with patch("app.time.time", return_value=START + 75):
            entry = {"date":DAY.isoformat(), "kind":"intervals_override", "intervals":[],
                     "edit_cutoff":int(START + 60), "edit_revision":self.app.store.manual_revision(DAY.isoformat())}
            # Use a freshly confirmed observation to make the current segment active.
            self.app.sample()
            with self.assertRaisesRegex(ValueError, "当前连接仍在记录"):
                self.app.save_manual_entries([entry])

    def test_resume_can_clear_pause_when_tracking_was_disabled_in_settings(self):
        self.app.store.save_settings({"tracking_enabled":False,
            "manual_pauses": [{"start": START, "end": None}]})
        with patch("app.time.time", return_value=START + 20):
            self.assertEqual(self.app.set_manual_pause(False), {"paused": False})
        self.assertFalse(self.app.store.settings()["tracking_enabled"])
        self.assertEqual(self.app.store.settings()["manual_pauses"][-1]["end"], START + 20)
