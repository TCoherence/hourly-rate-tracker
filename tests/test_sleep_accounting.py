"""Actual sleep events are distinct from missing samples and manual work."""
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import summarize
from store import Store, validate_settings

ZONE = ZoneInfo('America/Los_Angeles')
SETTINGS = {'annual_salary': 208800, 'timezone': 'America/Los_Angeles',
            'work_start': '09:00', 'work_end': '17:00', 'workdays': [0, 1, 2, 3, 4]}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def sleep(begin='2037-11-12T12:00', end='2037-11-12T13:00', state='connected', age=5):
    start = stamp(begin)
    return {'start': start, 'end': stamp(end) if end else None,
            'state': state, 'last_sample_ts': start - age}


def summary(entries, pause=False, rows=None, manual=None, now='2037-11-12T14:00', period='today'):
    return summarize(rows or [], {**SETTINGS, 'pause_on_sleep': pause}, period,
                     stamp(now), manual, entries)


class SleepCoreTests(unittest.TestCase):
    def test_explicit_pause_excludes_real_short_sleep_inside_a_connected_sample_pair(self):
        start = stamp('2037-11-12T12:00')
        rows = [{'ts': start, 'state': 'connected'}, {'ts': start + 30, 'state': 'connected'}]
        event = {'start': start + 5, 'end': start + 20, 'state': 'connected', 'last_sample_ts': start}
        result = summarize(rows, {**SETTINGS, 'pause_on_sleep': True}, 'today', start + 30,
                           sleep_intervals=[event])
        self.assertEqual(result['work_hours'], 15 / 3600)
        self.assertEqual(result['sleep_estimated_hours'], 0)
        self.assertTrue(result['pause_on_sleep'])
        self.assertTrue(any(x['source'] == 'sleep_paused' and x['state'] == 'unknown'
                            for x in result['timeline']))

    def test_default_pauses_and_does_not_estimate_sleep(self):
        now = stamp('2037-11-12T14:00')
        for events in ([sleep()], [sleep(state='disconnected')], [sleep(age=46)], [sleep(end=None)], []):
            with self.subTest(events=events):
                result = summarize([], SETTINGS, 'today', now, sleep_intervals=events)
                self.assertTrue(result['pause_on_sleep'])
                self.assertEqual(result['work_hours'], 0)
                self.assertEqual(result['sleep_estimated_hours'], 0)

    def test_toggle_recalculates_only_real_sleep_without_fabricating_observation_coverage(self):
        event = sleep()
        pause = summary([event], True)
        count = summary([event], False)
        self.assertEqual(pause['work_hours'], 0)
        self.assertEqual(count['work_hours'], 1)
        self.assertEqual(count['sleep_estimated_hours'], 1)
        self.assertEqual(count['observed_hours'], 0)
        self.assertEqual(count['income'], 800)
        day = next(d for d in count['days'] if d['date'] == '2037-11-12')
        self.assertEqual(day['sleep_estimated_hours'], 1)
        self.assertEqual(day['source'], 'sleep_estimate')
        self.assertEqual(day['status'], 'partial')
        self.assertEqual(event, sleep())

    def test_unknown_gaps_and_application_downtime_never_become_sleep_estimates(self):
        rows = [{'ts': stamp('2037-11-12T12:00'), 'state': 'connected'},
                {'ts': stamp('2037-11-12T13:00'), 'state': 'connected'}]
        result = summary([], rows=rows)
        self.assertEqual(result['work_hours'], 0)
        self.assertEqual(result['sleep_estimated_hours'], 0)

    def test_stale_future_missing_or_nonconnected_pre_sleep_state_never_estimates(self):
        for event in [sleep(state='disconnected'), sleep(state='unknown'), sleep(age=45.1),
                      sleep(age=-1), {**sleep(), 'last_sample_ts': None},
                      {**sleep(), 'last_sample_ts': float('nan')}]:
            with self.subTest(event=event):
                result = summary([event])
                self.assertEqual(result['work_hours'], 0)
                self.assertEqual(result['sleep_estimated_hours'], 0)
                self.assertTrue(any(x['source'] == 'sleep_unknown' for x in result['timeline']))
        self.assertEqual(summary([sleep(age=45)])['work_hours'], 1)

    def test_open_sleep_suppresses_work_but_never_estimates(self):
        start = stamp('2037-11-12T12:00')
        rows = [{'ts': start, 'state': 'connected'}, {'ts': start + 30, 'state': 'connected'}]
        event = {**sleep(end=None), 'start': start + 5}
        for pause in [True, False]:
            result = summary([event], pause, rows, now='2037-11-12T12:00:30')
            self.assertEqual(result['work_hours'], 5 / 3600)
            self.assertEqual(result['sleep_estimated_hours'], 0)

    def test_no_future_wake_can_authorize_retrospective_estimated_work(self):
        result = summary([sleep()], now='2037-11-12T12:30')
        self.assertEqual(result['work_hours'], 0)
        self.assertTrue(all(datetime.fromisoformat(x['end']).timestamp() <= stamp('2037-11-12T12:30')
                            for x in result['timeline']))

    def test_manual_intervals_override_paused_sleep_and_union_estimates(self):
        manual = [{'date': '2037-11-12', 'kind': 'intervals',
                   'intervals': [{'start': '12:30', 'end': '13:30'}]}]
        for pause, expected_work, estimated in [(True, 1, 0), (False, 1.5, 0.5)]:
            result = summary([sleep()], pause, manual=manual)
            self.assertEqual(result['work_hours'], expected_work)
            self.assertEqual(result['sleep_estimated_hours'], estimated)
            self.assertEqual(result['observed_hours'], 1)
            self.assertTrue(any(x['source'] == 'manual' for x in result['timeline']))

    def test_manual_daily_total_has_priority_over_sleep_estimates(self):
        event = sleep('2037-11-11T12:00', '2037-11-11T13:00')
        manual = [{'date': '2037-11-11', 'kind': 'daily_total', 'hours': 11}]
        result = summary([event], manual=manual, period='week')
        self.assertEqual(result['work_hours'], 11)
        self.assertEqual(result['sleep_estimated_hours'], 0)
        day = next(x for x in result['days'] if x['date'] == '2037-11-11')
        self.assertEqual(day['sleep_estimated_hours'], 0)
        self.assertEqual(day['source'], 'manual_estimate')

    def test_cross_midnight_and_weekend_hours_are_split_without_extra_weekend_income(self):
        event = sleep('2037-11-13T23:30', '2037-11-14T00:30')
        result = summary([event], now='2037-11-14T01:00', period='week')
        days = {x['date']: x for x in result['days']}
        self.assertEqual(result['sleep_estimated_hours'], 1)
        self.assertEqual(result['income'], 800)
        self.assertEqual(days['2037-11-13']['sleep_estimated_hours'], 0.5)
        self.assertEqual(days['2037-11-14']['sleep_estimated_hours'], 0.5)
        self.assertEqual(days['2037-11-14']['income'], 0)
        today = summary([event], now='2037-11-14T01:00')
        self.assertEqual(today['sleep_estimated_hours'], 0.5)
        self.assertEqual(today['income'], 0)

    def test_duplicate_sleep_input_and_simultaneous_vpn_samples_never_double_work(self):
        start = stamp('2037-11-12T12:00')
        rows = [{'ts': start + offset, 'state': 'connected'} for offset in range(0, 3601, 30)]
        result = summary([sleep(), sleep()], rows=rows)
        self.assertEqual(result['work_hours'], 1)
        self.assertEqual(result['sleep_estimated_hours'], 1)
        self.assertEqual(result['observed_hours'], 0)

    def test_invalid_sleep_records_cannot_add_work(self):
        result = summary([None, {}, {**sleep(), 'start': float('nan')},
                          {**sleep(), 'end': float('inf')}, {**sleep(), 'end': 0}])
        self.assertEqual(result['work_hours'], 0)


class SleepStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.store.close())

    def test_migration_defaults_and_strict_setting_validation(self):
        self.assertTrue(self.store.settings()['pause_on_sleep'])
        for chosen in (True, False):
            self.store.save_settings({'pause_on_sleep': chosen})
            self.store.close()
            self.store = Store(self.temp.name)
            self.assertIs(self.store.settings()['pause_on_sleep'], chosen)
        for value in [None, 'false', 0, 1, [], {}]:
            with self.assertRaises(ValueError):
                validate_settings({'pause_on_sleep': value})
        self.assertTrue(validate_settings({'annual_salary': None})['pause_on_sleep'])
        self.assertTrue(validate_settings({}, {'pause_on_sleep': True})['pause_on_sleep'])
        self.assertFalse(validate_settings({}, {'pause_on_sleep': False})['pause_on_sleep'])

    def test_paired_events_are_durable_and_do_not_modify_vpn_observations(self):
        self.store.record(95, 'connected')
        self.assertTrue(self.store.begin_sleep(100, 'connected', 95))
        self.assertTrue(self.store.end_sleep(200))
        self.store.close()
        self.store = Store(self.temp.name)
        self.assertEqual(self.store.sleep_intervals(),
                         [{'start': 100, 'end': 200, 'state': 'connected', 'last_sample_ts': 95}])
        self.assertEqual(self.store.db.execute('SELECT ts,state FROM observations').fetchall(), [(95, 'connected')])
        self.assertEqual(self.store.sleep_intervals(201), [])
        self.assertEqual(len(self.store.sleep_intervals(150)), 1)

    def test_duplicate_notifications_are_idempotent_and_stray_wake_has_no_effect(self):
        self.assertFalse(self.store.end_sleep(90))
        self.assertTrue(self.store.begin_sleep(100, 'connected', 95))
        self.assertFalse(self.store.begin_sleep(100, 'connected', 95))
        self.assertFalse(self.store.begin_sleep(101, 'connected', 95))
        self.assertTrue(self.store.end_sleep(200))
        self.assertFalse(self.store.end_sleep(201))
        self.assertFalse(self.store.begin_sleep(100, 'connected', 95))
        self.assertEqual(len(self.store.sleep_intervals()), 1)

    def test_restart_cannot_pair_old_sleep_with_new_process_wake(self):
        self.store.begin_sleep(100, 'connected', 95)
        self.store.close()
        self.store = Store(self.temp.name)
        self.store.abandon_open_sleep()
        self.assertFalse(self.store.end_sleep(500))
        self.assertEqual(self.store.sleep_intervals(), [])
        self.assertEqual(self.store.db.execute('SELECT abandoned FROM sleep_intervals').fetchone(), (1,))
        self.assertTrue(self.store.begin_sleep(600, 'connected', 595))
        self.assertTrue(self.store.end_sleep(700))
        self.assertEqual(len(self.store.sleep_intervals()), 1)

    def test_clock_rollback_and_invalid_events_never_make_negative_duration(self):
        self.store.begin_sleep(100, 'connected', 95)
        self.assertFalse(self.store.end_sleep(99))
        self.assertEqual(self.store.sleep_intervals(), [])
        for args in [(float('nan'), 'connected', 0), (100, 'bad', 99), (100, 'connected', float('inf'))]:
            with self.assertRaises(ValueError):
                self.store.begin_sleep(*args)
        with self.assertRaises(ValueError):
            self.store.end_sleep(float('nan'))


if __name__ == '__main__':
    unittest.main()
