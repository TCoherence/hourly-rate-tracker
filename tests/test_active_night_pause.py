"""Scheduled pauses must not masquerade as an actively protected VPN run."""
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import Application

ZONE = ZoneInfo("America/Los_Angeles")
DAY = "2026-11-15"


def stamp(hour, minute=0, second=0):
    return datetime(2026, 11, 15, hour, minute, second, tzinfo=ZONE).timestamp()


class ActiveNightPauseTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = Application(self.tmp.name, detector=lambda _: ("disabled", "test"))
        self.app.store.save_settings({"timezone": str(ZONE), "provider": "script", "status_script_path": "/tmp/example-status",
                                      "tracking_enabled": True, "night_pause_enabled": True})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def observe(self, timestamp):
        self.app.store.record(timestamp, "connected")
        self.app.state = "connected"
        self.app.last_checked = timestamp

    def detail(self, now):
        with patch("app.time.time", return_value=now):
            return self.app.history_day(DAY)

    def test_paused_connection_is_editable_until_new_sample_after_resumption(self):
        for sec in (stamp(8, 59, 30), stamp(8, 59, 45), stamp(8, 59, 59)):
            self.observe(sec)
        self.app.store.sync(stamp(8, 59, 59))
        self.assertIsNone(self.detail(stamp(8, 59, 59))["active_tracking"])
        # The clock has passed the resume boundary but no VPN sample has yet
        # confirmed that post-pause tracking has started.
        self.assertIsNone(self.detail(stamp(9, 0, 5))["active_tracking"])
        self.observe(stamp(9, 0, 15))
        active = self.detail(stamp(9, 0, 20))["active_tracking"]
        self.assertEqual(active["start"], datetime.fromtimestamp(stamp(9), ZONE).isoformat())
        self.assertEqual(active["locked_from"], datetime.fromtimestamp(stamp(9), ZONE).isoformat())

    def test_cross_midnight_pause_resumption_limits_old_continuous_vpn(self):
        self.app.store.save_settings({"night_pause_start": "22:00", "night_pause_end": "06:00"})
        for sec in (stamp(5, 59, 30), stamp(5, 59, 45), stamp(6), stamp(6, 0, 15)):
            self.observe(sec)
        self.app.store.sync(stamp(6, 0, 15))
        active = self.detail(stamp(6, 0, 20))["active_tracking"]
        self.assertEqual(active["locked_from"], datetime.fromtimestamp(stamp(6), ZONE).isoformat())

    def test_disabling_pause_restores_normal_connected_run(self):
        self.app.store.save_settings({"night_pause_enabled": False})
        self.observe(stamp(8, 59, 30))
        self.observe(stamp(8, 59, 45))
        self.app.store.sync(stamp(8, 59, 45))
        active = self.detail(stamp(8, 59, 50))["active_tracking"]
        self.assertEqual(active["start"], datetime.fromtimestamp(stamp(8, 59, 30), ZONE).isoformat())
