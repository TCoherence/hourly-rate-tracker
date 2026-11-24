"""Manual backfill is authenticated, reversible and separate from VPN samples."""

from datetime import datetime
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Application, LocalServer, handler_for

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2037, 11, 12, 22, tzinfo=ZONE).timestamp()


def backfill():
    entries = [{"date": f"2037-11-{day:02}", "kind": "daily_total", "hours": 11,
                "note": "模拟估算"} for day in (5, 6, 9, 10, 11)]
    entries.append({"date": "2037-11-12", "kind": "intervals", "note": "模拟时段",
                    "intervals": [{"start": "08:00", "end": "15:00"},
                                  {"start": "18:00", "end": "20:00"}]})
    return entries


class ManualAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Application(self.directory.name, detector=lambda _: ("disabled", "test"))
        self.app.store.save_settings({"annual_salary": 208800, "timezone": str(ZONE)})
        start = datetime(2037, 11, 12, 19, tzinfo=ZONE).timestamp()
        for offset in range(0, 1801, 30):
            self.app.store.record(start + offset, "connected")
        self.app.store.sync(NOW)
        self.original = self.app.store.published_samples()
        self.original_sync = self.app.store.sync_status()
        self.original_settings = self.app.store.settings()
        self.server = LocalServer(("127.0.0.1", 0), handler_for(self.app))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.clock = patch("app.time.time", return_value=NOW)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.directory.cleanup()

    def request(self, path, body=None, authenticated=True, csrf=True):
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if authenticated:
            headers["X-Session-Token"] = self.app.session_token
        if csrf:
            headers["X-CSRF-Token"] = self.app.token
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request("GET" if body is None else "POST", path,
                               body=None if body is None else json.dumps(body), headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_history_month_requires_session_and_valid_month(self):
        self.assertEqual(self.request('/api/history-month?month=2037-11', authenticated=False)[0], 401)
        self.assertEqual(self.request('/api/history-month?month=2037-13')[0], 400)
        status, result = self.request('/api/history-month?month=2037-11')
        self.assertEqual(status, 200)
        self.assertEqual(len(result['days']), 30)

    def test_example_backfill_is_64_hours_without_overlapping_vpn_double_count(self):
        before = self.request("/api/dashboard?period=month")[1]
        self.assertEqual(before["summary"]["work_hours"], 0.5)
        status, saved = self.request("/api/manual-entries", {"entries": backfill()})
        self.assertEqual(status, 200)
        self.assertEqual(saved["today"], "2037-11-12")
        self.assertEqual(saved["timezone"], str(ZONE))
        self.assertEqual(len(saved["entries"]), 6)
        for period, hours in (("today", 9), ("week", 42), ("month", 64)):
            with self.subTest(period=period):
                result = self.request("/api/dashboard?period=" + period)[1]["summary"]
                self.assertEqual(result["work_hours"], hours)
        self.assertEqual(self.app.store.published_samples(), self.original)
        self.assertEqual(self.app.store.sync_status(), self.original_sync)
        self.assertEqual(self.app.store.settings(), self.original_settings)

    def test_save_is_idempotent_and_replace_and_delete_recalculate_in_same_minute(self):
        for _ in range(2):
            self.assertEqual(self.request("/api/manual-entries", {"entries": backfill()})[0], 200)
        self.assertEqual(len(self.request("/api/manual-entries")[1]["entries"]), 6)
        entry = {"date": "2037-11-11", "kind": "daily_total", "hours": 10}
        self.assertEqual(self.request("/api/manual-entries", {"entries": [entry]})[0], 200)
        self.assertEqual(self.request("/api/dashboard?period=month")[1]["summary"]["work_hours"], 63)
        self.assertEqual(self.request("/api/manual-entries/delete", {"date": "2037-11-12"})[0], 200)
        result = self.request("/api/dashboard?period=today")[1]["summary"]
        self.assertEqual(result["work_hours"], 0.5)
        self.assertEqual(result["manual_days"], 0)
        self.assertEqual(self.app.store.published_samples(), self.original)

    def test_future_portion_of_today_is_not_counted_early(self):
        with patch("app.time.time", return_value=datetime(2037, 11, 12, 19, 30, tzinfo=ZONE).timestamp()):
            self.assertEqual(self.request("/api/manual-entries", {"entries": backfill()})[0], 200)
            result = self.request("/api/dashboard?period=today")[1]["summary"]
        self.assertEqual(result["work_hours"], 8.5)

    def test_demo_does_not_include_real_manual_records(self):
        before = self.request("/api/dashboard?period=month&demo=1")[1]["summary"]
        self.request("/api/manual-entries", {"entries": backfill()})
        after = self.request("/api/dashboard?period=month&demo=1")[1]["summary"]
        self.assertEqual(before, after)
        self.assertEqual(after["manual_days"], 0)

    def test_private_reads_and_writes_require_authentication_and_csrf(self):
        self.assertEqual(self.request("/api/manual-entries", authenticated=False)[0], 401)
        for path, body in (("/api/manual-entries", {"entries": backfill()}),
                           ("/api/manual-entries/delete", {"date": "2037-11-12"})):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, body, authenticated=False)[0], 403)
                self.assertEqual(self.request(path, body, csrf=False)[0], 403)
        self.assertEqual(self.app.store.manual_entries(), [])

    def test_invalid_batch_is_rejected_without_partial_write(self):
        entries = backfill()
        entries[-1]["intervals"] = [{"start": "21:00", "end": "19:00"}]
        self.assertEqual(self.request("/api/manual-entries", {"entries": entries})[0], 400)
        self.assertEqual(self.app.store.manual_entries(), [])
        for path, body in (("/api/manual-entries", {"unexpected": []}),
                           ("/api/manual-entries/delete", {"date": "bad"})):
            self.assertEqual(self.request(path, body)[0], 400)
        self.assertEqual(self.app.store.published_samples(), self.original)

    def test_present_tail_end_to_end_preserves_unknown_and_stays_closed(self):
        status, snapshot = self.request('/api/history-day?date=2037-11-12')
        self.assertEqual(status, 200)
        self.assertIs(snapshot['present_manual_tail_supported'], True)
        item = {'date':'2037-11-12', 'kind':'intervals_override',
                'edit_cutoff':snapshot['edit_cutoff'], 'edit_revision':snapshot['edit_revision'],
                'intervals':[{'start':'19:00','end':'19:30'}, {'start':'21:00','end':'22:00'}],
                'present_end':'22:00', 'present_closed':True}
        status, response = self.request('/api/manual-entries', {'entries':[item]})
        self.assertEqual(status, 200, response)
        self.assertEqual(self.app.store.published_samples(), self.original)
        with patch('app.time.time', return_value=NOW + 15 * 60):
            status, reopened = self.request('/api/history-day?date=2037-11-12')
            self.assertEqual(status, 200)
            self.assertIs(reopened['manual_entry']['present_closed'], True)
            self.assertEqual(reopened['protected_tail_intervals'], [{'start':'21:00','end':'22:00'}])
            gap = next(part for part in reopened['segments'] if part['start'][11:16] == '19:30')
            self.assertEqual(gap['state'], 'unknown')
            self.assertEqual(gap['end'][11:16], '21:00')
            after = next(part for part in reopened['segments'] if part['start'][11:16] == '22:00')
            self.assertEqual(after['state'], 'unknown')
            self.assertEqual(self.request('/api/dashboard?period=today')[1]['summary']['work_hours'], 1.5)
        self.assertEqual(self.app.store.published_samples(), self.original)

    def test_present_closed_without_tail_marker_is_persisted_via_http(self):
        same_minute = datetime(2037, 11, 12, 19, 30, 23, tzinfo=ZONE).timestamp()
        with patch('app.time.time', return_value=same_minute):
            status, snapshot = self.request('/api/history-day?date=2037-11-12')
            self.assertEqual(status, 200)
            self.assertEqual(snapshot['edit_cutoff'], int(same_minute // 60) * 60)
            item = {'date':'2037-11-12', 'kind':'intervals_override',
                    'edit_cutoff':snapshot['edit_cutoff'], 'edit_revision':snapshot['edit_revision'],
                    'intervals':[{'start':'19:00','end':'19:30'}], 'present_closed':True}
            status, response = self.request('/api/manual-entries', {'entries':[item]})
            self.assertEqual(status, 200, response)
        with patch('app.time.time', return_value=same_minute + 15 * 60):
            status, reopened = self.request('/api/history-day?date=2037-11-12')
        self.assertEqual(status, 200)
        self.assertIs(reopened['manual_entry']['present_closed'], True)
        self.assertEqual(reopened['editable_intervals'], [{'start':'19:00','end':'19:30'}])
        self.assertEqual(reopened['protected_tail_intervals'], [])


if __name__ == "__main__":
    unittest.main()
