"""Night pause only changes accounting; manual entries remain authoritative."""
from datetime import date, datetime
from unittest import TestCase
from zoneinfo import ZoneInfo

from core import calendar_month, history_day, night_pause_state, summarize

ZONE = ZoneInfo('America/Los_Angeles')
BASE = {'timezone': str(ZONE), 'annual_salary': 208800,
        'night_pause_enabled': True, 'night_pause_start': '00:00',
        'night_pause_end': '09:00', 'pause_on_sleep': True}


def ts(day, hour, minute=0, fold=0):
    return datetime(2037, 11, day, hour, minute, tzinfo=ZONE, fold=fold).timestamp()


def observations(start, finish):
    return [{'ts': float(x), 'state': 'connected'} for x in range(int(start), int(finish) + 1, 30)]


class NightPauseTests(TestCase):
    def test_schedule_recalculates_without_changing_vpn_and_all_views_agree(self):
        start, end = ts(13, 0), ts(13, 10)
        rows = observations(start, end)
        before = [dict(row) for row in rows]
        result = summarize(rows, BASE, 'week', end)
        daily = next(d for d in result['days'] if d['date'] == '2037-11-13')
        self.assertEqual(daily['work_hours'], 1)
        self.assertEqual(daily['vpn_work_hours'], 10)
        month = calendar_month(rows, BASE, date(2037, 11, 1), end)
        self.assertEqual(next(d for d in month if d['date'] == daily['date'])['work_hours'], 1)
        detail = history_day(rows, BASE, date(2037, 11, 13), end)
        self.assertTrue(any(x['source'] == 'night_paused' and x['state'] == 'unknown' for x in detail['segments']))
        self.assertEqual(detail['editable_intervals'], [{'start':'09:00', 'end':'10:00'}])
        self.assertEqual(rows, before)
        self.assertEqual(summarize(rows, {**BASE, 'night_pause_enabled':False}, 'week', end)['work_hours'], 10)

    def test_manual_intervals_daily_total_and_override_take_priority(self):
        start, end = ts(13, 0), ts(13, 10)
        rows = observations(start, end)
        def total(entry):
            return summarize(rows, BASE, 'week', ts(14,10), manual_entries=[entry])['work_hours']
        self.assertEqual(total({'date':'2037-11-13','kind':'intervals','intervals':[{'start':'02:00','end':'04:00'}]}), 3)
        self.assertEqual(total({'date':'2037-11-13','kind':'intervals_override','intervals':[{'start':'01:00','end':'03:00'}]}), 2)
        # Daily totals are valid only on completed dates.
        self.assertEqual(summarize(rows, BASE, 'week', ts(14, 10), manual_entries=[{'date':'2037-11-13','kind':'daily_total','hours':11}])['work_hours'], 11)

    def test_unknown_gaps_are_never_invented_as_observed(self):
        rows = [{'ts':ts(13,1), 'state':'connected'}, {'ts':ts(13,2), 'state':'connected'}]
        result = summarize(rows, BASE, 'week', ts(13,10))
        day = next(d for d in result['days'] if d['date'] == '2037-11-13')
        self.assertEqual(day['work_hours'], 0)
        self.assertEqual(day['observed_hours'], 0)
        self.assertEqual(day['status'], 'unknown')
        self.assertFalse(any(x['source'] == 'night_paused' for x in result['timeline']))

    def test_sleep_estimate_is_paused_but_manual_can_restore_it(self):
        start, end = ts(13, 1), ts(13, 2)
        sleeps = [{'start':start,'end':end,'state':'connected','last_sample_ts':start-5}]
        config = {**BASE, 'pause_on_sleep':False}
        result = summarize([], config, 'week', ts(13,10), sleep_intervals=sleeps)
        self.assertEqual(result['work_hours'], 0)
        self.assertEqual(result['sleep_estimated_hours'], 0)
        self.assertTrue(any(x['source'] == 'night_paused' for x in result['timeline']))
        manual = [{'date':'2037-11-13','kind':'intervals','intervals':[{'start':'01:00','end':'02:00'}]}]
        self.assertEqual(summarize([], config, 'week', ts(13,10), manual, sleeps)['work_hours'], 1)

    def test_cross_midnight_custom_window(self):
        rows = observations(ts(13,21), ts(14,2))
        cfg = {**BASE, 'night_pause_start':'22:00', 'night_pause_end':'01:00'}
        result = summarize(rows, cfg, 'week', ts(14,2))
        self.assertEqual(result['work_hours'], 2)
        self.assertTrue(night_pause_state(ts(14,0), cfg)[0])
        self.assertEqual(night_pause_state(ts(14,1), cfg), (False, ts(14,1)))

    def test_spring_forward_and_repeated_fall_hour(self):
        start = datetime(2037,3,8,0,tzinfo=ZONE).timestamp()
        end = datetime(2037,3,8,4,tzinfo=ZONE).timestamp()
        spring = {**BASE, 'night_pause_start':'00:00','night_pause_end':'03:00'}
        self.assertEqual(summarize(observations(start,end), spring, 'today', end)['work_hours'], 1)
        # Both 01:30–01:45 occurrences are paused, with the interval between
        # the repeated occurrences left active.
        start, end = ts(1,0), ts(1,3)
        fall = {**BASE, 'night_pause_start':'01:30','night_pause_end':'01:45'}
        result = summarize(observations(start,end), fall, 'today', end)
        self.assertEqual(result['work_hours'], 3.5)
        self.assertEqual(night_pause_state(ts(1,1,35,fold=0), fall)[0], True)
        self.assertEqual(night_pause_state(ts(1,1,10,fold=1), fall), (False, ts(1,1,45,fold=0)))
        self.assertEqual(night_pause_state(ts(1,1,50,fold=1), fall), (False, ts(1,1,45,fold=1)))

    def test_new_year_and_disabled_resume(self):
        start = datetime(2037,12,31,23,tzinfo=ZONE).timestamp()
        end = datetime(2038,1,1,10,tzinfo=ZONE).timestamp()
        result = summarize(observations(start,end), BASE, 'rolling_year', end)
        self.assertEqual(result['work_hours'], 2)
        self.assertEqual(night_pause_state(end, {**BASE,'night_pause_enabled':False}), (False,None))
