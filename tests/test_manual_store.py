"""Manual corrections persist separately from the original VPN observations."""

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import Store


NOW = datetime(2037, 11, 12, 20, 0, tzinfo=timezone.utc).timestamp()


def daily(day="2037-11-11", hours=11, **fields):
    return {"date": day, "kind": "daily_total", "hours": hours, **fields}


def intervals(day="2037-11-12", spans=None, **fields):
    return {"date": day, "kind": "intervals",
            "intervals": [{"start": start, "end": end}
                          for start, end in (spans if spans is not None else [("09:00", "18:00")])],
            **fields}


class ManualStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)
        self.addCleanup(lambda: self.store.close())

    def save(self, entries):
        return self.store.save_manual_entries(entries, now=NOW)

    def test_separate_table_has_one_json_payload_per_date(self):
        columns = self.store.db.execute("PRAGMA table_info(manual_entries)").fetchall()
        self.assertEqual([(column[1], column[5]) for column in columns], [("date", 1), ("payload", 0)])
        self.assertEqual(self.store.manual_entries(), [])
        self.save([daily()])
        day, payload = self.store.db.execute("SELECT date,payload FROM manual_entries").fetchone()
        self.assertEqual(day, "2037-11-11")
        self.assertEqual(json.loads(payload), daily(hours=11.0, note=""))

    def test_upsert_replaces_date_and_identical_save_does_not_write(self):
        self.save([daily()])
        previous_changes = self.store.db.total_changes
        self.save([daily(hours=11.0, note="")])
        self.assertEqual(self.store.db.total_changes, previous_changes)
        result = self.save([daily(hours=8, note="修正当天总时长")])
        self.assertEqual(result, [daily(hours=8.0, note="修正当天总时长")])
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM manual_entries").fetchone()[0], 1)
        result = self.save([intervals(day="2037-11-11")])
        self.assertEqual(result, [intervals(day="2037-11-11", note="")])

    def test_results_are_sorted_and_survive_reopening(self):
        expected = [daily("2037-11-09", 0.0, note="休息"), daily("2037-11-11", 11.0, note="")]
        self.assertEqual(self.save([daily(), daily("2037-11-09", 0, note="休息")]), expected)
        self.store.close()
        self.store = Store(self.directory.name)
        self.assertEqual(self.store.manual_entries(), expected)
        self.assertEqual(self.store.delete_manual_entry("2037-11-09"), expected[1:])
        self.assertEqual(self.store.delete_manual_entry("2037-11-09"), expected[1:])
        self.store.close()
        self.store = Store(self.directory.name)
        self.assertEqual(self.store.manual_entries(), expected[1:])

    def test_intervals_are_sorted_overlap_merged_and_allow_midnight_end(self):
        entry = intervals(spans=[("15:00", "18:00"), ("09:00", "12:00"),
                                 ("11:00", "15:00"), ("21:00", "24:00")])
        expected = intervals(spans=[("09:00", "15:00"), ("15:00", "18:00"), ("21:00", "24:00")], note="")
        self.assertEqual(self.save([entry]), [expected])
        previous_changes = self.store.db.total_changes
        self.save([expected])
        self.assertEqual(self.store.db.total_changes, previous_changes)

    def test_today_future_interval_end_is_retained_for_summary_to_clip(self):
        entry = intervals(spans=[("19:00", "24:00")])
        self.assertEqual(self.save([entry]), [{**entry, "note": ""}])

    def test_daily_total_accepts_zero_and_twenty_four(self):
        result = self.save([daily("2037-11-10", 0), daily("2037-11-11", 24)])
        self.assertEqual([entry["hours"] for entry in result], [0.0, 24.0])

    def test_original_observations_settings_and_publication_watermark_are_untouched(self):
        self.store.save_settings({"annual_salary": 100000})
        self.store.record(100, "connected")
        self.store.sync(now=200)
        self.store.record(210, "unknown")
        original_rows = self.store.db.execute("SELECT * FROM observations ORDER BY id").fetchall()
        original_meta = self.store.db.execute("SELECT * FROM meta ORDER BY key").fetchall()
        published = self.store.published_samples()
        sync_status = self.store.sync_status()
        for operation in (lambda: self.save([daily()]),
                          lambda: self.save([daily(hours=8)]),
                          lambda: self.store.delete_manual_entry("2037-11-11")):
            operation()
            self.assertEqual(self.store.db.execute("SELECT * FROM observations ORDER BY id").fetchall(), original_rows)
            self.assertEqual(self.store.db.execute("SELECT * FROM meta ORDER BY key").fetchall(), original_meta)
            self.assertEqual(self.store.published_samples(), published)
            self.assertEqual(self.store.sync_status(), sync_status)

    def test_today_and_future_dates_follow_settings_timezone(self):
        near_midnight = datetime(2037, 11, 12, 7, 30, tzinfo=timezone.utc).timestamp()
        # It is still November 11 in Los Angeles.
        for entry in (daily("2037-11-11"), intervals("2037-11-12")):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                self.store.save_manual_entries([entry], now=near_midnight)
        self.store.save_manual_entries([intervals("2037-11-11")], now=near_midnight)
        self.store.save_settings({"timezone": "Asia/Tokyo"})
        self.store.save_manual_entries([daily("2037-11-11"), intervals("2037-11-12")], now=near_midnight)
        self.assertEqual(len(self.store.manual_entries()), 2)

    def test_invalid_entry_batches_are_atomic_and_errors_do_not_echo_payload(self):
        original = self.save([daily()])
        invalid = [
            None, [], "PRIVATE_PAYLOAD", {},
            {"date": "2037-11-10", "kind": "PRIVATE_PAYLOAD"},
            {"date": "2037-11-10", "kind": "daily_total"},
            daily("2037-11-10", 1, unsupported="PRIVATE_PAYLOAD"),
            daily("2037-11-10", 1, intervals=[]),
            daily("2037-11-10", True), daily("2037-11-10", "11"),
            daily("2037-11-10", float("nan")), daily("2037-11-10", float("inf")),
            daily("2037-11-10", -1), daily("2037-11-10", 24.01),
            daily("2037-11-10", 10 ** 1000),
            daily("2037-11-10", 1, note=None), daily("2037-11-10", 1, note="字" * 501),
            daily("2037-11-12"), daily("2037-11-13"), intervals("2037-11-13"),
            daily("2037-02-30"), daily("20371110"), daily("2037-1-10"),
            daily(20371110), intervals(spans=[]),
            intervals(spans=[("09:00", "10:00")] * 13),
            intervals(spans=[("24:00", "24:00")]), intervals(spans=[("09:00", "09:00")]),
            intervals(spans=[("18:00", "09:00")]), intervals(spans=[("9:00", "12:00")]),
            intervals(spans=[("09:00", "24:01")]), intervals(spans=[("09:00", "12:60")]),
            intervals(spans=[("０９:00", "12:00")]), intervals(spans=[(None, "12:00")]),
            {"date": "2037-11-10", "kind": "intervals", "intervals": "PRIVATE_PAYLOAD"},
            {"date": "2037-11-10", "kind": "intervals", "intervals": [None]},
            {"date": "2037-11-10", "kind": "intervals",
             "intervals": [{"start": "09:00", "end": "10:00", "extra": "PRIVATE_PAYLOAD"}]},
        ]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ValueError) as raised:
                self.save([daily(hours=7), entry])
            self.assertNotIn("PRIVATE_PAYLOAD", str(raised.exception))
            self.assertEqual(self.store.manual_entries(), original)

    def test_duplicate_date_batch_does_not_replace_existing_row(self):
        original = self.save([daily()])
        with self.assertRaisesRegex(ValueError, "只能出现一次"):
            self.save([daily(hours=3), intervals("2037-11-11")])
        self.assertEqual(self.store.manual_entries(), original)

    def test_batch_limit_and_note_limit(self):
        entries = [daily((date(2037, 11, 11) - timedelta(days=index)).isoformat(), 1)
                   for index in range(367)]
        for invalid in (entries, [], None, {"entries": entries[:1]}):
            with self.subTest(value=type(invalid)), self.assertRaises(ValueError):
                self.save(invalid)
            self.assertEqual(self.store.manual_entries(), [])
        entries[0]["note"] = "字" * 500
        self.assertEqual(len(self.save(entries[:366])), 366)

    def test_sql_failure_rolls_back_entire_batch(self):
        original = self.save([daily()])
        self.store.db.execute("""CREATE TRIGGER reject_test_date BEFORE INSERT ON manual_entries
                                WHEN NEW.date = '2037-11-10' BEGIN
                                SELECT RAISE(ABORT, 'test write failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.save([daily(hours=3), daily("2037-11-10", 8)])
        self.assertEqual(self.store.manual_entries(), original)

    def test_delete_rejects_invalid_date_without_touching_rows(self):
        original = self.save([daily()])
        for value in (None, "20371111", "2037-02-30", "2037-11-11' OR 1=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.delete_manual_entry(value)
            self.assertEqual(self.store.manual_entries(), original)


if __name__ == "__main__":
    unittest.main()
