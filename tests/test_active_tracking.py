"""Current connections are displayed and protected without inventing VPN time."""
from datetime import datetime
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from app import Application

ZONE = ZoneInfo('America/Los_Angeles')
DAY = '2026-11-15'
def at(hour, minute=0, second=0):
    return datetime(2026,11,15,hour,minute,second,tzinfo=ZONE).timestamp()

class ActiveTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = Application(self.tmp.name, detector=lambda _: ('disabled', 'test'))
        self.app.store.save_settings({'provider':'script', 'status_script_path':'/tmp/example-status','tracking_enabled':True})
    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()
    def observe(self, timestamp, state):
        self.app.store.record(timestamp, state)
        self.app.last_checked, self.app.state = timestamp, state
    def detail(self, now):
        with patch('app.time.time', return_value=now):
            return self.app.history_day(DAY)
    def test_connected_run_moves_cutoff_before_start_and_keeps_pending(self):
        self.observe(at(8,0), 'disconnected')
        self.observe(at(8,0,15), 'disconnected')
        self.app.store.sync(at(8,0,15))
        self.observe(at(8,0,30), 'connected')
        self.observe(at(8,0,45), 'connected')
        self.observe(at(8,1), 'connected')
        self.app.store.sync(at(8,1))
        self.observe(at(8,1,15), 'connected')  # not yet published
        result = self.detail(at(8,1,20))
        self.assertEqual(result['edit_cutoff'], at(8))
        self.assertEqual(result['active_tracking']['start'], datetime.fromtimestamp(at(8,0,30), ZONE).isoformat())
        self.assertEqual(result['active_tracking']['last_confirmed'], datetime.fromtimestamp(at(8,1,15), ZONE).isoformat())
        self.assertFalse(result['active_tracking']['save_blocked'])
        self.assertEqual(result['editable_intervals'], [])
    def test_unavailable_when_disabled_disconnected_stale_asleep_or_unknown(self):
        self.observe(at(9), 'connected')
        self.app.store.sync(at(9))
        self.assertIsNotNone(self.detail(at(9,0,15))['active_tracking'])
        self.assertIsNone(self.detail(at(9,1))['active_tracking'])
        self.app.system_sleeping = True
        self.assertIsNone(self.detail(at(9,0,15))['active_tracking'])
        self.app.system_sleeping = False
        self.app.state = 'unknown'
        self.assertIsNone(self.detail(at(9,0,15))['active_tracking'])
        self.app.state = 'disconnected'
        self.assertIsNone(self.detail(at(9,0,15))['active_tracking'])
        self.app.store.save_settings({'tracking_enabled':False})
        self.app.state = 'connected'
        self.assertIsNone(self.detail(at(9,0,15))['active_tracking'])
    def test_open_power_event_and_prior_day_are_not_currently_connected(self):
        self.observe(at(9), 'connected')
        self.app.store.sync(at(9))
        with patch('app.time.time', return_value=at(9,0,15)):
            self.assertIsNone(self.app.history_day('2026-11-14')['active_tracking'])
        self.app.power_events.put(('sleep', at(9,0,10), 'connected', at(9)))
        self.assertIsNone(self.detail(at(9,0,15))['active_tracking'])
    def test_gap_and_short_sleep_prevent_claiming_older_run(self):
        self.observe(at(9), 'connected')
        self.observe(at(9,2), 'connected')
        self.observe(at(9,2,15), 'connected')
        self.app.store.sync(at(9,2,15))
        self.assertEqual(self.detail(at(9,2,20))['active_tracking']['start'], datetime.fromtimestamp(at(9,2), ZONE).isoformat())
        self.app.store.begin_sleep(at(9,2,16), 'connected', at(9,2,15))
        self.app.store.end_sleep(at(9,2,20))
        self.observe(at(9,2,30), 'connected')
        self.assertEqual(self.detail(at(9,2,35))['active_tracking']['start'], datetime.fromtimestamp(at(9,2,30), ZONE).isoformat())
    def test_midnight_and_equal_timestamp_do_not_extend_to_previous_day(self):
        previous = datetime(2026,11,14,23,59,50,tzinfo=ZONE).timestamp()
        self.observe(previous, 'connected')
        self.observe(at(0,0,5), 'unknown')
        self.observe(at(0,0,5), 'connected')  # last observation at same time wins
        self.observe(at(0,0,20), 'connected')
        self.app.store.sync(at(0,0,20))
        active = self.detail(at(0,0,25))['active_tracking']
        self.assertEqual(active['start'], datetime.fromtimestamp(at(0,0,5), ZONE).isoformat())
        self.assertEqual(active['locked_from'], datetime.fromtimestamp(at(0), ZONE).isoformat())
    def test_connection_started_after_open_rejects_stale_later_cutoff(self):
        # A transient error can hide a continuous connection when a draft is
        # opened; once sampling recovers, the older cutoff is unsafe.
        for minute, second in ((4,0),(4,15),(4,30),(4,45),(5,0)):
            self.observe(at(10,minute,second), 'connected')
        self.app.store.sync(at(10,5))
        self.app.state = 'unknown'
        snapshot = self.detail(at(10,5,5))
        self.observe(at(10,5,15), 'connected')
        payload = {'date': DAY, 'kind':'intervals_override', 'intervals':[],
                   'edit_cutoff':int(snapshot['edit_cutoff']), 'edit_revision':snapshot['edit_revision']}
        with patch('app.time.time', return_value=at(10,5,20)):
            with self.assertRaisesRegex(ValueError, '进行中'):
                self.app.save_manual_entries([payload])
    def test_save_cannot_override_active_run_or_discard_prior_correction(self):
        self.observe(at(9), 'connected')
        self.observe(at(9,0,15), 'connected')
        self.app.store.sync(at(9,0,15))
        revision = self.app.store.manual_revision(DAY)
        unsafe = {'date': DAY, 'kind':'intervals_override', 'intervals':[], 'edit_cutoff':int(at(9,1)), 'edit_revision':revision}
        with patch('app.time.time', return_value=at(9,1)):
            with self.assertRaisesRegex(ValueError, '进行中'):
                self.app.save_manual_entries([unsafe])
        # A correction already saved before this version must never silently be truncated.
        prior = {'date': DAY, 'kind':'intervals_override', 'intervals':[{'start':'08:00','end':'09:00'}], 'edit_cutoff':int(at(9,1)), 'edit_revision':revision}
        self.app.store.save_manual_entries([prior], now=at(9,2))
        old = self.app.store.manual_entries()
        self.assertTrue(self.detail(at(9,0,30))['active_tracking']['save_blocked'])
        candidate = {'date': DAY, 'kind':'intervals_override', 'intervals':[], 'edit_cutoff':int(at(9)), 'edit_revision':self.app.store.manual_revision(DAY)}
        with patch('app.time.time', return_value=at(9,0,30)):
            with self.assertRaisesRegex(ValueError, '先前修正'):
                self.app.save_manual_entries([candidate])
            with self.assertRaisesRegex(ValueError, '先撤销'):
                self.app.save_manual_entries([{'date':DAY,'kind':'intervals','intervals':[{'start':'10:00','end':'11:00'}]}])
        self.assertEqual(self.app.store.manual_entries(), old)
        self.observe(at(9,0,40), 'disconnected')
        self.assertIsNone(self.detail(at(9,0,45))['active_tracking'])

if __name__ == '__main__': unittest.main()
