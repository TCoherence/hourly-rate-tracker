"""Corrections use the snapshot boundary; future samples and sleep still apply."""
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import Application
from core import summarize
from exporting import serialize_backup, validate_backup
import json

ZONE = ZoneInfo('America/Los_Angeles')
DAY = '2026-11-14'
def at(hour, minute=0, second=0, day=14):
    return datetime(2026, 11, day, hour, minute, second, tzinfo=ZONE).timestamp()

def points(start, end):
    return [{'ts': t, 'state': 'connected'} for t in range(int(start), int(end) + 1, 15)]

def correction(cutoff, revision, intervals):
    return {'date': DAY, 'kind':'intervals_override', 'intervals':intervals,
            'edit_cutoff':int(cutoff), 'edit_revision':revision}

class TodayCorrectionTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.app = Application(self.temp.name, detector=lambda _:('disabled','test'))
        self.app.store.save_settings({'timezone':str(ZONE), 'pause_on_sleep':True})
    def tearDown(self):
        self.app.close()
        self.temp.cleanup()
    def test_split_survives_reopen_and_new_samples_after_cutoff(self):
        for p in points(at(9), at(10)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(10))
        with patch('app.time.time', return_value=at(10,0,23)):
            snapshot = self.app.history_day(DAY)
        split = [{'start':'09:00','end':'09:30'}, {'start':'09:30','end':'10:00'}]
        self.app.store.save_manual_entries([correction(snapshot['edit_cutoff'], snapshot['edit_revision'], split)], now=at(10,0,23))
        for p in points(at(10,0,15), at(11)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(11))
        self.app.close()
        self.app = Application(self.temp.name, detector=lambda _:('disabled','test'))
        for now in (at(11,0,23), at(1,day=15)):
            with patch('app.time.time', return_value=now):
                detail = self.app.history_day(DAY)
            self.assertEqual(detail['manual_entry']['intervals'], split)
            self.assertEqual(detail['editable_intervals'], [
                {'start':'09:00','end':'09:30'}, {'start':'09:30','end':'11:00'}])
            connected = [s for s in detail['segments'] if s['source'] == 'manual_override' and s['state'] == 'connected']
            self.assertEqual(len(connected), 2)
            result = summarize(self.app.store.published_samples(), self.app.store.settings(), 'week', now,
                               self.app.store.manual_entries(), [])
            recorded = next(d for d in result['days'] if d['date'] == DAY)
            self.assertAlmostEqual(recorded['work_hours'], 2)

    def test_continues_after_cutoff_and_across_midnight(self):
        original = {'date':DAY, 'kind':'intervals', 'intervals':[{'start':'11:30','end':'13:00'}]}
        self.app.store.save_manual_entries([original], now=at(9))
        for p in points(at(9), at(12)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(12))
        with patch('app.time.time', return_value=at(10,0,23)):
            snapshot = self.app.history_day(DAY)
        self.assertEqual(snapshot['edit_cutoff'], at(10))
        self.assertEqual(snapshot['editable_intervals'], [{'start':'09:00','end':'10:00'}])
        self.app.store.save_manual_entries([correction(at(10), snapshot['edit_revision'],
            [{'start':'09:30','end':'10:00'}])], now=at(10,20))
        saved = self.app.store.manual_entries()
        self.assertEqual(saved[0]['edit_cutoff'], at(10))
        rows = self.app.store.published_samples()
        settings = self.app.store.settings()
        # The 20 minutes while editing, subsequent samples and a previously
        # planned manual tail remain in effect, even after the date changes.
        result = summarize(rows, settings, 'today', at(13,30), saved, [])
        self.assertAlmostEqual(result['work_hours'], 3.5)
        result = summarize(rows, settings, 'week', at(1,day=15), saved, [])
        day = next(d for d in result['days'] if d['date'] == DAY)
        self.assertAlmostEqual(day['work_hours'], 3.5)
        self.assertEqual(self.app.store.published_samples(), rows)
        self.app.store.delete_manual_entry(DAY)
        self.assertEqual(self.app.store.manual_entries()[0]['intervals'], original['intervals'])
    def test_revision_conflict_and_cutoff_validation(self):
        revision = self.app.store.manual_revision(DAY)
        with self.assertRaises(ValueError):
            self.app.store.save_manual_entries([correction(at(11), revision,
                [{'start':'10:00','end':'11:00'}])], now=at(10))
        with self.assertRaises(ValueError):
            self.app.store.save_manual_entries([correction(at(10), revision,
                [{'start':'09:00','end':'10:01'}])], now=at(10,30))
        self.app.store.save_manual_entries([correction(at(10), revision, [])], now=at(10,30))
        with self.assertRaisesRegex(ValueError, '变化'):
            self.app.store.save_manual_entries([correction(at(10), revision, [])], now=at(10,30))
    def test_repeated_correction_keeps_tail_and_sleep_pause(self):
        original = {'date':DAY, 'kind':'intervals', 'intervals':[{'start':'12:00','end':'13:00'}]}
        self.app.store.save_manual_entries([original], now=at(9))
        rev = self.app.store.manual_revision(DAY)
        self.app.store.save_manual_entries([correction(at(10), rev,
            [{'start':'09:00','end':'10:00'}])], now=at(10,5))
        rev = self.app.store.manual_revision(DAY)
        self.app.store.save_manual_entries([correction(at(11), rev,
            [{'start':'09:30','end':'10:00'},{'start':'10:30','end':'11:00'}])], now=at(11,5))
        rows = points(at(9), at(12))
        sleeps = [{'start':at(11,30),'end':at(12),'state':'connected','last_sample_ts':at(11,29,50)}]
        result = summarize(rows, self.app.store.settings(), 'today', at(13,30), self.app.store.manual_entries(), sleeps)
        self.assertAlmostEqual(result['work_hours'], 2.5)
    def test_cutoff_never_passes_latest_published_sample(self):
        for p in points(at(9), at(9,59,30)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(9,59,30))
        for p in points(at(9,59,45), at(10,2)):
            self.app.store.record(p['ts'], p['state'])
        with patch('app.time.time', return_value=at(10,2,30)):
            snapshot = self.app.history_day(DAY)
        self.assertEqual(snapshot['edit_cutoff'], at(9,59))
        self.assertEqual(snapshot['editable_intervals'], [{'start':'09:00','end':'09:59'}])
        self.app.store.save_manual_entries([correction(snapshot['edit_cutoff'], snapshot['edit_revision'], [])], now=at(10,3))
        self.app.store.sync(at(10,3))
        summary = summarize(self.app.store.published_samples(), self.app.store.settings(), 'today', at(10,3), self.app.store.manual_entries(), [])
        self.assertAlmostEqual(summary['work_hours'], 3/60)
        today = next(d for d in summary['days'] if d['date'] == DAY)
        self.assertEqual(today['manual_kind'], 'intervals_override')
        self.app.store.delete_manual_entry(DAY)
        self.assertEqual(self.app.store.manual_entries(), [])

    def test_present_tail_does_not_extend_the_correction_or_erase_unknown(self):
        for p in points(at(9), at(10)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(10))
        with patch('app.time.time', return_value=at(12,0,23)):
            snapshot = self.app.history_day(DAY)
            self.assertEqual(snapshot['edit_cutoff'], at(10))
            self.assertIs(snapshot['present_manual_tail_supported'], True)
            self.assertEqual(snapshot['protected_tail_intervals'], [])
            entry = correction(snapshot['edit_cutoff'], snapshot['edit_revision'], [
                {'start':'09:00','end':'10:00'}, {'start':'11:00','end':'12:00'}])
            entry['present_end'] = '12:00'
            self.app.save_manual_entries([entry])
            result = self.app.history_day(DAY)
            self.assertEqual(result['editable_intervals'], [{'start':'09:00','end':'10:00'}])
            self.assertEqual(result['protected_tail_intervals'], [{'start':'11:00','end':'12:00'}])
        saved = self.app.store.manual_entries()[0]
        self.assertEqual(saved['edit_cutoff'], at(10))
        self.assertEqual(saved['intervals'], [{'start':'09:00','end':'10:00'}])
        self.assertEqual(saved['tail_intervals'], [{'start':'11:00','end':'12:00'}])
        self.assertIs(saved['present_closed'], True)
        self.assertNotIn('present_end', saved)
        gap = [p for p in result['segments'] if p['start'].startswith(DAY + 'T10:00')]
        self.assertEqual(gap[0]['state'], 'unknown')
        self.assertEqual(gap[0]['end'][11:16], '11:00')
        work = [p for p in result['segments'] if p['start'].startswith(DAY + 'T11:00')]
        self.assertEqual(work[0]['state'], 'connected')
        self.assertEqual(len(self.app.store.published_samples()), len(points(at(9), at(10))))
        with patch('app.time.time', return_value=at(12,15,23)):
            later = self.app.history_day(DAY)
        self.assertIs(later['manual_entry']['present_closed'], True)
        self.assertEqual(later['protected_tail_intervals'], [{'start':'11:00','end':'12:00'}])
        self.assertTrue(any(part['start'][11:16] == '12:00' and part['state'] == 'unknown'
                            for part in later['segments']))
        payload = serialize_backup(self.app.store.export_snapshot(), at(12,0,23))
        backup = json.loads(payload)
        restored_snapshot = validate_backup(backup)
        self.assertEqual(backup['manual_entries'][0]['tail_intervals'], saved['tail_intervals'])
        with TemporaryDirectory() as directory:
            restored = Application(directory, detector=lambda _:('disabled','test'))
            try:
                restored.store.restore_snapshot(restored_snapshot)
                self.assertEqual(restored.store.manual_entries()[0], saved)
                with patch('app.time.time', return_value=at(12,0,23)):
                    restored_result = restored.history_day(DAY)
                self.assertEqual(restored_result['segments'], result['segments'])
            finally:
                restored.close()

    def test_present_tail_preserves_existing_tail_and_future_automatic_samples(self):
        for p in points(at(9), at(10)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(10))
        with patch('app.time.time', return_value=at(12,0,23)):
            snapshot = self.app.history_day(DAY)
            first = correction(snapshot['edit_cutoff'], snapshot['edit_revision'], [
                {'start':'09:00','end':'10:00'}, {'start':'11:00','end':'12:00'}])
            first['present_end'] = '12:00'
            self.app.save_manual_entries([first])
        with patch('app.time.time', return_value=at(13,0,23)):
            revision = self.app.store.manual_revision(DAY)
            second = correction(at(10), revision, [
                {'start':'09:00','end':'10:00'}, {'start':'12:30','end':'13:00'}])
            second['present_end'] = '13:00'
            self.app.save_manual_entries([second])
        self.assertEqual(self.app.store.manual_entries()[0]['tail_intervals'], [
            {'start':'11:00','end':'12:00'}, {'start':'12:30','end':'13:00'}])
        with patch('app.time.time', return_value=at(13,0,23)):
            reopened = self.app.history_day(DAY)
        self.assertEqual(reopened['protected_tail_intervals'], [
            {'start':'11:00','end':'12:00'}, {'start':'12:30','end':'13:00'}])
        for p in points(at(13,30), at(14)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(14))
        with patch('app.time.time', return_value=at(14,0,23)):
            detail = self.app.history_day(DAY)
        self.assertTrue(any(part['start'][11:16] == '13:30' and part['state'] == 'connected'
                            for part in detail['segments']))

    def test_present_tail_keeps_prior_manual_entry_recoverable(self):
        original = {'date':DAY, 'kind':'intervals', 'intervals':[
            {'start':'09:00','end':'10:00'}, {'start':'11:30','end':'11:45'}]}
        self.app.store.save_manual_entries([original], now=at(10))
        for p in points(at(9), at(10)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(10))
        with patch('app.time.time', return_value=at(12,0,23)):
            snapshot = self.app.history_day(DAY)
            item = correction(snapshot['edit_cutoff'], snapshot['edit_revision'], [
                {'start':'09:00','end':'10:00'}, {'start':'11:00','end':'12:00'}])
            item['present_end'] = '12:00'
            self.app.save_manual_entries([item])
        self.app.store.delete_manual_entry(DAY)
        restored = self.app.store.manual_entries()[0]
        self.assertEqual(restored['kind'], original['kind'])
        self.assertEqual(restored['intervals'], original['intervals'])

    def test_present_tail_validation_and_active_race(self):
        rev = self.app.store.manual_revision(DAY)
        def candidate(end='12:00', marker='12:00'):
            item = correction(at(10), rev, [{'start':'09:00','end':end}])
            item['present_end'] = marker
            return item
        with patch('app.time.time', return_value=at(12,0,23)):
            for bad in (candidate('12:01','12:01'), candidate('12:00','11:59'),
                        candidate('10:00','10:00')):
                with self.assertRaises(ValueError):
                    self.app.save_manual_entries([bad])
            # Simulate tracking becoming active after the editor read its snapshot.
            with patch.object(self.app, 'active_tracking', return_value={'locked_from_ts':at(11)}):
                with self.assertRaisesRegex(ValueError, '状态已变化'):
                    self.app.save_manual_entries([candidate()])
        self.assertEqual(self.app.store.manual_entries(), [])

    def test_present_tail_rejects_unknown_stale_sleep_and_pending_power_event(self):
        self.app.store.save_settings({'provider':'script', 'status_script_path':'/tmp/example-status',
                                      'tracking_enabled':True, 'night_pause_enabled':False})
        item = correction(at(10), self.app.store.manual_revision(DAY), [{'start':'09:00','end':'12:00'}])
        item['present_end'] = '12:00'
        now = at(12,0,23)
        with patch('app.time.time', return_value=now):
            for state, checked in [('unknown', now), ('disconnected', at(11,0)), ('connected', now)]:
                self.app.state, self.app.last_checked = state, checked
                with self.subTest(state=state, checked=checked):
                    with self.assertRaisesRegex(ValueError, '状态已变化'):
                        self.app.save_manual_entries([item])
            self.app.state, self.app.last_checked = 'disconnected', now
            self.app.system_sleeping = True
            with self.assertRaisesRegex(ValueError, '状态已变化'):
                self.app.save_manual_entries([item])
            self.app.system_sleeping = False
            self.app.power_events.put(('sleep', now, 'disconnected', now))
            with self.assertRaisesRegex(ValueError, '状态已变化'):
                self.app.save_manual_entries([item])
        self.assertEqual(self.app.store.manual_entries(), [])

    def test_present_tail_accepts_fresh_disconnected_or_explicit_pause(self):
        for paused in (False, True):
            with self.subTest(paused=paused), TemporaryDirectory() as directory:
                app = Application(directory, detector=lambda _:('disabled','test'))
                try:
                    app.store.save_settings({'timezone':str(ZONE), 'provider':'script',
                                             'status_script_path':'/tmp/example-status',
                                             'tracking_enabled':True, 'night_pause_enabled':False,
                                             'manual_pauses':[{'start':at(11), 'end':None}] if paused else []})
                    now = at(12,0,23)
                    app.state = 'unknown' if paused else 'disconnected'
                    app.last_checked = at(11) if paused else now
                    item = correction(at(10), app.store.manual_revision(DAY), [{'start':'09:00','end':'12:00'}])
                    item['present_end'] = '12:00'
                    with patch('app.time.time', return_value=now):
                        app.save_manual_entries([item])
                    self.assertEqual(app.store.manual_entries()[0]['tail_intervals'], [{'start':'10:00','end':'12:00'}])
                finally:
                    app.close()

    def test_power_event_during_tail_save_rolls_back_transaction(self):
        now = at(12,0,23)
        original_save = self.app.store.save_manual_entries
        def interrupted(entries, now=None, precommit=None):
            def inject_event():
                self.app.on_power_event('sleep', at(12,0,5))
                precommit()
            return original_save(entries, now=now, precommit=inject_event)
        item = correction(at(10), self.app.store.manual_revision(DAY), [{'start':'09:00','end':'12:00'}])
        item['present_end'] = '12:00'
        with patch('app.time.time', return_value=now), patch.object(self.app.store, 'save_manual_entries', side_effect=interrupted):
            with self.assertRaisesRegex(ValueError, '状态已变化'):
                self.app.save_manual_entries([item])
        self.assertEqual(self.app.store.manual_entries(), [])

    def test_present_closed_survives_reopen_and_backup(self):
        for p in points(at(9), at(10)):
            self.app.store.record(p['ts'], p['state'])
        self.app.store.sync(at(10))
        with patch('app.time.time', return_value=at(12,0,23)):
            snapshot = self.app.history_day(DAY)
            item = correction(snapshot['edit_cutoff'], snapshot['edit_revision'], [{'start':'09:00','end':'10:00'}])
            item['present_closed'] = True
            self.app.save_manual_entries([item])
            reopened = self.app.history_day(DAY)
        self.assertIs(reopened['manual_entry']['present_closed'], True)
        self.assertEqual(reopened['editable_intervals'], [{'start':'09:00','end':'10:00'}])
        self.assertEqual(reopened['protected_tail_intervals'], [])
        backup = json.loads(serialize_backup(self.app.store.export_snapshot(), at(12,0,23)))
        restored = validate_backup(backup)
        with TemporaryDirectory() as directory:
            copy = Application(directory, detector=lambda _:('disabled','test'))
            try:
                copy.store.restore_snapshot(restored)
                with patch('app.time.time', return_value=at(12,0,23)):
                    self.assertIs(copy.history_day(DAY)['manual_entry']['present_closed'], True)
            finally:
                copy.close()

    def test_present_closed_must_be_boolean_and_can_preserve_fixed_tail(self):
        revision = self.app.store.manual_revision(DAY)
        with patch('app.time.time', return_value=at(12,0,23)):
            item = correction(at(10), revision, [{'start':'09:00','end':'10:00'}])
            item['present_closed'] = 'yes'
            with self.assertRaises(ValueError):
                self.app.save_manual_entries([item])
            item = correction(at(10), revision, [{'start':'09:00','end':'10:30'}])
            item.update(present_closed=True, present_end='10:30')
            self.app.save_manual_entries([item])
            saved = self.app.store.manual_entries()[0]
            self.assertIs(saved['present_closed'], True)
            self.assertEqual(saved['tail_intervals'], [{'start':'10:00','end':'10:30'}])
            self.assertEqual(self.app.history_day(DAY)['manual_entry']['present_closed'], True)

    def test_empty_snapshot_can_correct_unless_samples_are_pending(self):
        with patch('app.time.time', return_value=at(10,1,30)):
            self.assertEqual(self.app.history_day(DAY)['edit_cutoff'], at(10,1))
        self.app.store.record(at(10), 'connected')
        with patch('app.time.time', return_value=at(10,1,30)):
            self.assertEqual(self.app.history_day(DAY)['edit_cutoff'], at(0))

    def test_dst_today_is_rejected_and_unavailable(self):
        now = datetime(2026, 11, 1, 12, tzinfo=ZONE).timestamp()
        with patch('app.time.time', return_value=now):
            detail = self.app.history_day('2026-11-01')
        self.assertFalse(detail['today_override_available'])
        with self.assertRaisesRegex(ValueError, '偏移'):
            self.app.store.save_manual_entries([{'date':'2026-11-01','kind':'intervals_override',
                'intervals':[], 'edit_cutoff':detail['edit_cutoff'], 'edit_revision':detail['edit_revision']}], now=now)
