"""No display or VPN state is changed; monitor and clock are simulated."""
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Application
from binary_backup import snapshot_file, restore_sqlite_file
from exporting import json_backup, validate_backup
from screen_alerts import ScreenAlertTracker
from screen_monitor import DisplayMonitor


class FakePower:
    def __init__(self, callback):
        self.status, self.error = 'running', None
    def start(self): pass
    def stop(self): pass


class FakeDisplay:
    def __init__(self):
        self.asleep, self.error = True, None
    def read(self): return self.asleep


class FakeGraphics:
    def __init__(self, values): self.values = values
    def CGGetOnlineDisplayList(self, capacity, displays, count):
        ctypes.cast(count, ctypes.POINTER(ctypes.c_uint32)).contents.value = len(self.values)
        if displays is not None:
            for i in range(min(capacity, len(self.values))): displays[i] = i + 1
        return 0
    def CGDisplayIsAsleep(self, display): return int(self.values[display - 1])


class ScreenMonitorTests(unittest.TestCase):
    def test_all_displays_must_be_asleep_and_empty_is_unknown(self):
        self.assertIs(DisplayMonitor(platform='darwin', library=FakeGraphics([True, True])).read(), True)
        self.assertIs(DisplayMonitor(platform='darwin', library=FakeGraphics([True, False])).read(), False)
        self.assertIsNone(DisplayMonitor(platform='darwin', library=FakeGraphics([])).read())
        self.assertIsNone(DisplayMonitor(platform='linux').read())

    def test_exact_threshold_gaps_and_clock_changes_break_continuity(self):
        tracker, alerts = ScreenAlertTracker(), []
        for step in range(960): tracker.observe(1000 + step * 15, step * 15, True, 4, alerts)
        self.assertEqual(alerts, [])
        tracker.observe(1000 + 14400, 14400, True, 4, alerts)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['start'], 1000)
        self.assertEqual(alerts[0]['end'], 15400)
        tracker.observe(15415, 14415, False, 4, alerts)
        self.assertIsNone(tracker.alert_id)
        tracker.observe(15500, 14500, True, 4, alerts)
        tracker.observe(15600, 14600, True, 4, alerts)
        self.assertEqual(tracker.start, 15600)
        tracker.observe(15615, 14630, True, 4, alerts)
        self.assertEqual(tracker.start, 15615)

    def test_capacity_never_discards_pending_alerts(self):
        alerts = [{'id':str(i), 'start':1, 'end':2, 'status':'pending'} for i in range(1000)]
        tracker = ScreenAlertTracker(max_gap=4000)
        tracker.observe(0, 0, True, 1, alerts)
        tracker.observe(3600, 3600, True, 1, alerts)
        self.assertTrue(tracker.full)
        self.assertEqual(len(alerts), 1000)
        alerts[0]['status'] = 'kept'
        tracker.observe(3615, 3615, True, 1, alerts)
        self.assertFalse(tracker.full)
        self.assertEqual(len(alerts), 1000)
        self.assertNotIn('0', [a['id'] for a in alerts])


class ScreenAlertApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.display = FakeDisplay()
        self.state = 'connected'
        self.app = Application(self.temp.name, detector=lambda _: (self.state, 'test'),
                               power_monitor_factory=FakePower, display_monitor_factory=lambda:self.display)
        self.app.store.save_settings({'provider':'script', 'status_script_path':'/tmp/example-status', 'tracking_enabled':True,
                                      'timezone':'UTC', 'screen_alert_hours':1})
        self.addCleanup(self.app.close)

    def sample(self, offset):
        with patch('app.time.time', return_value=1_900_000_000 + offset), patch('app.time.monotonic', return_value=offset):
            self.app.sample()

    def test_only_overlap_triggers_and_keep_does_not_edit_work(self):
        for t in range(0, 3601, 15): self.sample(t)
        settings = self.app.store.settings()
        alerts = self.app.screen_alerts(settings)
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]['active'])
        with self.assertRaises(ValueError): self.app.keep_screen_alert(alerts[0]['id'])
        self.display.asleep = False
        self.sample(3615)
        before = self.app.store.export_snapshot()['observations']
        self.assertEqual(self.app.keep_screen_alert(alerts[0]['id']), {'ok':True})
        self.assertEqual(self.app.screen_alerts(self.app.store.settings()), [])
        self.assertEqual(self.app.store.export_snapshot()['observations'], before)

    def test_intermittent_unknown_sleep_pause_or_disabled_breaks_interval(self):
        for t in range(0, 1801, 15): self.sample(t)
        self.state = 'unknown'
        self.sample(1815)
        self.state = 'connected'
        for t in range(1830, 3631, 15): self.sample(t)
        self.assertEqual(self.app.screen_alerts(self.app.store.settings()), [])
        self.app.system_sleeping = True
        self.sample(3645)
        self.app.system_sleeping = False
        self.assertIsNone(self.app.screen_tracker.start)
        self.app.store.save_settings({'manual_pauses':[{'start':1_900_003_660,'end':None}]})
        self.sample(3660)
        self.assertIsNone(self.app.screen_tracker.start)
        self.app.store.save_settings({'screen_alert_enabled':False})
        self.sample(3675)
        self.assertIsNone(self.app.screen_tracker.start)

    def test_night_pause_breaks_continuity_and_does_not_count_toward_threshold(self):
        self.app.store.save_settings({'night_pause_enabled':True, 'night_pause_start':'23:00', 'night_pause_end':'01:00'})
        base = datetime(2034, 1, 2, 22, 30, tzinfo=timezone.utc).timestamp()
        for offset in range(0, 3601, 15):
            with patch('app.time.time', return_value=base + offset), patch('app.time.monotonic', return_value=offset):
                self.app.sample()
        self.assertIsNone(self.app.screen_tracker.start)
        self.assertEqual(self.app.screen_alerts(self.app.store.settings()), [])

    def test_startup_already_asleep_begins_at_first_observation_not_before(self):
        self.sample(0)
        self.assertEqual(self.app.screen_tracker.start, 1_900_000_000)
        self.app.reset_screen_tracker()
        self.sample(3600)
        self.assertEqual(self.app.screen_tracker.start, 1_900_003_600)
        self.assertEqual(self.app.screen_alerts(self.app.store.settings()), [])

    def test_detect_failure_does_not_bridge_unknown_samples(self):
        self.sample(0)
        self.sample(15)
        self.app.detector = lambda _: (_ for _ in ()).throw(OSError('test failure'))
        with patch('app.time.time', return_value=1_900_000_030), patch('app.time.monotonic', return_value=30):
            self.app.safe_sample()
        self.assertIsNone(self.app.screen_tracker.start)
        self.app.detector = lambda _: ('connected', 'test')
        self.sample(45)
        self.assertEqual(self.app.screen_tracker.start, 1_900_000_045)

    def test_settings_read_failure_does_not_retry_even_with_active_reminder(self):
        self.app.screen_tracker.start = 100
        self.app.screen_tracker.last = 200
        self.app.screen_tracker.last_mono = 100
        self.app.screen_tracker.alert_id = 'active'
        with patch.object(self.app.store, 'settings', side_effect=OSError('test failure')) as failing:
            self.app.safe_sample()
            self.assertEqual(failing.call_count, 1)
        self.assertIsNone(self.app.screen_tracker.start)
        self.assertEqual(self.app.state, 'unknown')

    def test_screen_failure_does_not_change_vpn_state(self):
        self.display.read = lambda: (_ for _ in ()).throw(RuntimeError('test failure'))
        self.sample(0)
        self.assertEqual(self.app.state, 'connected')
        self.assertFalse(self.app.screen_monitor_state['available'])

    def test_reminder_finalization_failure_never_drops_sleep_event(self):
        self.sample(0)
        self.app.on_power_event('sleep', 1_900_000_015)
        with patch.object(self.app, '_end_screen_candidate', side_effect=OSError('test failure')):
            self.assertTrue(self.app.process_power_events())
        sleeps = self.app.store.sleep_intervals(0)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(sleeps[0]['start'], 1_900_000_015)
        self.assertTrue(self.app.system_sleeping)
        self.assertFalse(self.app.screen_monitor_state['available'])

    def test_reminder_finalization_failure_does_not_block_settings_or_manual_pause(self):
        with patch.object(self.app, '_end_screen_candidate', side_effect=OSError('test failure')):
            self.assertEqual(self.app.settings({'screen_alert_hours':2})['screen_alert_hours'], 2)
            self.assertEqual(self.app.set_manual_pause(True), {'paused':True})
        self.assertEqual(self.app.store.settings()['screen_alert_hours'], 2)
        self.assertIsNone(self.app.store.settings()['manual_pauses'][-1]['end'])
        self.assertFalse(self.app.screen_monitor_state['available'])

    def test_reminder_finalization_failure_does_not_block_service_close(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application(directory, detector=lambda _: ('connected', 'test'),
                              power_monitor_factory=FakePower, display_monitor_factory=FakeDisplay)
            app.store.save_settings({'provider':'script', 'status_script_path':'/tmp/example-status', 'tracking_enabled':True})
            app.sample()
            with patch.object(app, '_end_screen_candidate', side_effect=OSError('test failure')):
                app.close()
            with sqlite3.connect(str(Path(directory) / 'records.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT state FROM observations ORDER BY id DESC LIMIT 1').fetchone(), ('unknown',))

    def test_restart_and_json_sqlite_restore_do_not_invent_active_interval(self):
        self.sample(0)
        self.sample(15)
        self.app.reset_screen_tracker()  # process restart has no remembered interval
        self.sample(30)
        self.assertEqual(self.app.screen_tracker.start, 1_900_000_030)
        before = self.app.store.export_snapshot()
        old = dict(before, settings={k:v for k,v in before['settings'].items() if not k.startswith('screen_alert')})
        self.assertEqual(validate_backup(json_backup(old, 1_900_000_040))['settings']['screen_alerts'], [])
        backup = snapshot_file(self.app.store)
        try:
            restore_sqlite_file(self.app, backup)
            self.assertIsNone(self.app.screen_tracker.start)
            self.assertFalse(self.app.store.settings()['tracking_enabled'])
        finally:
            backup.unlink(missing_ok=True)

    def test_old_sqlite_backup_without_screen_settings_restores(self):
        backup = snapshot_file(self.app.store)
        try:
            with sqlite3.connect(str(backup)) as db:
                old = json.loads(db.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0])
                old = {k:v for k,v in old.items() if not k.startswith('screen_alert')}
                db.execute("UPDATE meta SET value=? WHERE key='settings'", (json.dumps(old),))
            self.sample(0)
            restore_sqlite_file(self.app, backup)
            settings = self.app.store.settings()
            self.assertEqual(settings['screen_alert_hours'], 4)
            self.assertEqual(settings['screen_alerts'], [])
            self.assertIsNone(self.app.screen_tracker.start)
        finally:
            backup.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
