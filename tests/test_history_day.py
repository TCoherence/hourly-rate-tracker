"""Real daily segments and reversible corrections preserve original observations."""
import json
import http.client
import threading
import unittest
from datetime import datetime, date, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo
from app import Application, LocalServer, handler_for
from core import history_day, summarize

ZONE = ZoneInfo('America/Los_Angeles')
NOW = datetime(2026, 11, 14, 12, tzinfo=ZONE).timestamp()
def at(day, hour, minute=0, second=0):
    return datetime(2026, 11, day, hour, minute, second, tzinfo=ZONE).timestamp()
def samples(start, end):
    return [{'ts': start + i, 'state': 'connected'} for i in range(0, int(end-start)+1, 15)]
def entry(kind, intervals):
    return {'date':'2026-11-13','kind':kind,'intervals':intervals,'note':'test'}

class HistoryDayTests(unittest.TestCase):
    def test_split_boundaries_survive_storage_and_appear_in_history(self):
        with TemporaryDirectory() as directory:
            app = Application(directory, detector=lambda _:('disabled','test'))
            app.store.save_settings({'timezone':str(ZONE)})
            spans = [{'start':'09:00','end':'10:00'}, {'start':'10:00','end':'12:00'}]
            app.store.save_manual_entries([entry('intervals_override', spans)], now=NOW)
            app.close()
            app = Application(directory, detector=lambda _:('disabled','test'))
            try:
                self.assertEqual(app.store.manual_entries()[0]['intervals'], spans)
                with patch('app.time.time', return_value=NOW):
                    detail = app.history_day('2026-11-13')
                    self.assertEqual(detail['editable_intervals'], spans)
                    connected = [s for s in detail['segments'] if s['state'] == 'connected']
                    self.assertEqual(len(connected), 2)
                    self.assertIn('10:00:00', connected[0]['end'])
                    self.assertIn('10:00:00', connected[1]['start'])
                    day = next(d for d in app.dashboard('week')['summary']['days'] if d['date'] == '2026-11-13')
                    self.assertAlmostEqual(day['work_hours'], 3)
            finally: app.close()

    def test_raw_seconds_unknown_gap_sleep_and_minute_draft(self):
        rows = samples(at(13,9,0,13), at(13,10,0,13)) + samples(at(13,11,0,16),at(13,12,0,16))
        sleeps = [{'start':at(13,11,20), 'end':at(13,11,30), 'state':'connected', 'last_sample_ts':at(13,11,19,46)}]
        result = history_day(rows, {'timezone':str(ZONE),'pause_on_sleep':True}, date(2026,11,13), NOW, [], sleeps)
        self.assertIn('09:00:13', result['raw_segments'][1]['start'])
        self.assertTrue(any(s['state']=='unknown' and s['source']=='vpn' for s in result['segments']))
        self.assertTrue(any(s['source']=='sleep_paused' for s in result['segments']))
        self.assertEqual(result['editable_intervals'], [{'start':'09:00','end':'10:00'},{'start':'11:00','end':'11:20'},{'start':'11:30','end':'12:00'}])
    def test_override_replaces_day_and_raw_and_reversal_are_preserved(self):
        with TemporaryDirectory() as directory:
            app = Application(directory, detector=lambda _:('disabled','test'))
            try:
                original = samples(at(13,9),at(13,15))
                for row in original: app.store.record(row['ts'],row['state'])
                app.store.sync(NOW)
                prior = entry('intervals',[{'start':'17:00','end':'18:00'}])
                app.store.save_manual_entries([prior], now=NOW)
                initial = app.store.published_samples()
                override = entry('intervals_override',[{'start':'09:00','end':'11:00'},{'start':'10:30','end':'12:00'}])
                app.store.save_manual_entries([override], now=NOW)
                app.store.save_manual_entries([entry('intervals_override',[{'start':'09:00','end':'12:00'}])], now=NOW)
                with patch('app.time.time',return_value=NOW):
                    detail=app.history_day('2026-11-13')
                    self.assertTrue(any(s['source']=='manual_override' and s['state']=='disconnected' for s in detail['segments']))
                    self.assertTrue(any(s['source']=='manual_override' and s['state']=='connected' for s in detail['segments']))
                    self.assertTrue(any(s['source']=='vpn' and s['state']=='connected' for s in detail['raw_segments']))
                    result=app.dashboard('week')['summary']
                    d=next(d for d in result['days'] if d['date']=='2026-11-13')
                    self.assertAlmostEqual(d['work_hours'],3)
                    self.assertAlmostEqual(d['vpn_work_hours'],6)
                self.assertEqual(app.store.published_samples(),initial)
                app.store.delete_manual_entry('2026-11-13')
                self.assertEqual(app.store.manual_entries(),[prior])
                self.assertEqual(app.store.published_samples(),initial)
            finally: app.close()
    def test_override_rejects_today_and_total_does_not_fabricate_times(self):
        with TemporaryDirectory() as directory:
            app=Application(directory, detector=lambda _:('disabled','test'))
            try:
                bad={**entry('intervals_override',[{'start':'09:00','end':'10:00'}]), 'date':'2026-11-14'}
                with self.assertRaises(ValueError): app.store.save_manual_entries([bad],now=NOW)
                app.store.save_manual_entries([{'date':'2026-11-13','kind':'daily_total','hours':10}],now=NOW)
                with patch('app.time.time',return_value=NOW): detail=app.history_day('2026-11-13')
                self.assertIsNone(detail['editable_intervals'])
                self.assertIn('不能推测',detail['editable_reason'])
            finally: app.close()
    def test_dst_date_declines_unsafe_prefill(self):
        result=history_day([], {'timezone':str(ZONE)}, date(2026,11,1), NOW, [], [])
        self.assertIsNone(result['editable_intervals'])
        self.assertIn('时区偏移',result['editable_reason'])

    def test_cross_midnight_is_clipped_and_other_day_unaffected(self):
        start = datetime(2026, 10, 31, 23, 59, 30, tzinfo=ZONE).timestamp()
        finish = datetime(2026, 11, 1, 0, 0, 30, tzinfo=ZONE).timestamp()
        rows = samples(start, finish)
        settings = {'timezone':str(ZONE),'pause_on_sleep':True}
        correction = {'date':'2026-10-31','kind':'intervals_override',
                      'intervals':[{'start':'23:00','end':'24:00'}]}
        result = history_day(rows, settings, date(2026,10,31), NOW, [correction], [])
        self.assertEqual(result['editable_intervals'],[{'start':'23:00','end':'24:00'}])
        self.assertTrue(any(s['state']=='connected' and '23:59:30' in s['start'] for s in result['raw_segments']))
        result2 = history_day(rows, settings, date(2026,11,1), NOW, [correction], [])
        self.assertTrue(any(s['state']=='connected' and s['source']=='vpn' and '00:00:00' in s['start'] for s in result2['segments']))

    def test_history_http_requires_auth_and_valid_date(self):
        with TemporaryDirectory() as directory:
            app = Application(directory, detector=lambda _:('disabled','test'))
            server = LocalServer(('127.0.0.1', 0), handler_for(app))
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':0.01}, daemon=True)
            thread.start()
            try:
                def get(path, auth):
                    conn = http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=3)
                    headers = {'Host':'127.0.0.1:' + str(server.server_address[1])}
                    if auth: headers['X-Session-Token'] = app.session_token
                    conn.request('GET',path,headers=headers)
                    response=conn.getresponse(); data=json.loads(response.read()); conn.close()
                    return response.status, data
                self.assertEqual(get('/api/history-day?date=2026-11-13',False)[0],401)
                with patch('app.time.time',return_value=NOW):
                    self.assertEqual(get('/api/history-day?date=2026-11-13',True)[0],200)
                    self.assertEqual(get('/api/history-day?date=2026-11-15',True)[0],400)
                    self.assertEqual(get('/api/history-day?date=2026-13-99',True)[0],400)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2); app.close()

if __name__ == '__main__': unittest.main()
