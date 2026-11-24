"""Focused heatmap follows local calendar months across year and month ends."""

from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import summarize

ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {"annual_salary": 208800, "timezone": str(ZONE), "workdays": [0, 1, 2, 3, 4]}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def observations(begin, end):
    return [{"ts": value, "state": "connected"}
            for value in range(int(stamp(begin)), int(stamp(end)) + 1, 30)]


class HeatmapWindowTests(unittest.TestCase):
    def test_window_includes_endpoints_and_all_calendar_days_independent_of_period(self):
        now = stamp("2037-11-12T22:00")
        previous = None
        for period in ("today", "month", "year", "rolling_year"):
            result = summarize([], SETTINGS, period, now)
            days = result["heatmap_recent_days"]
            self.assertEqual(result["heatmap_window"], {"start": "2037-08-12", "end": "2038-02-12"})
            expected = []
            current = date(2037, 8, 12)
            while current <= date(2038, 2, 12):
                expected.append(current.isoformat())
                current += timedelta(days=1)
            self.assertEqual([day["date"] for day in days], expected)
            if previous is not None:
                self.assertEqual(days, previous)
            previous = days

    def test_new_year_window_preserves_previous_year_records_and_salary(self):
        rows = observations("2025-12-31T09:00", "2025-12-31T17:00")
        settings = {**SETTINGS, "salary_history": [
            {"effective_from": "2026-01-01", "annual_salary": 417600}]}
        manual = [{"date": "2026-01-02", "kind": "daily_total", "hours": 8}]
        result = summarize(rows, settings, "today", stamp("2026-01-05T12:00"), manual)
        days = {day["date"]: day for day in result["heatmap_recent_days"]}
        self.assertEqual(result["heatmap_window"], {"start": "2025-10-05", "end": "2026-04-05"})
        self.assertEqual(days["2025-12-31"]["work_hours"], 8)
        self.assertEqual(days["2025-12-31"]["actual_rate"], 100)
        self.assertEqual(days["2026-01-02"]["work_hours"], 8)
        self.assertEqual(days["2026-01-02"]["actual_rate"], 200)
        self.assertEqual(result["work_hours"], 0)  # The heatmap does not change today's totals.
        self.assertTrue(all(day["date"].startswith("2026-") for day in result["days"]))

    def test_short_month_end_and_leap_year_are_clamped(self):
        for today, start, end in (
            ("2026-05-31", "2026-02-28", "2026-08-31"),
            ("2024-05-31", "2024-02-29", "2024-08-31"),
            ("2026-11-30", "2026-08-30", "2027-02-28"),
            ("2023-11-30", "2023-08-30", "2024-02-29"),
        ):
            with self.subTest(today=today):
                result = summarize([], SETTINGS, "today", stamp(today + "T12:00"))
                self.assertEqual(result["heatmap_window"], {"start": start, "end": end})
                self.assertEqual(result["heatmap_recent_days"][0]["date"], start)
                self.assertEqual(result["heatmap_recent_days"][-1]["date"], end)

    def test_window_uses_configured_timezone_date(self):
        now = datetime.fromisoformat("2027-01-01T02:00:00+00:00").timestamp()
        pacific = summarize([], SETTINGS, "today", now)
        tokyo = summarize([], {**SETTINGS, "timezone": "Asia/Tokyo"}, "today", now)
        self.assertEqual(pacific["heatmap_window"], {"start": "2026-09-30", "end": "2027-03-31"})
        self.assertEqual(tokyo["heatmap_window"], {"start": "2026-10-01", "end": "2027-04-01"})

    def test_existing_year_heatmap_matches_overlapping_recent_dates(self):
        rows = observations("2037-11-09T09:00", "2037-11-09T17:00")
        rows += observations("2037-11-12T00:00", "2037-11-12T01:00")
        manual = [{"date": "2037-11-11", "kind": "daily_total", "hours": 11}]
        result = summarize(rows, SETTINGS, "week", stamp("2037-11-12T01:00"), manual)
        yearly = {day["date"]: day for day in result["days"]}
        for day in result["heatmap_recent_days"]:
            if day["date"] in yearly:
                self.assertEqual(day, yearly[day["date"]])
        self.assertEqual(len(result["days"]), 365)
        self.assertEqual([day["date"] for day in result["period_days"]],
                         ["2037-11-09", "2037-11-10", "2037-11-11", "2037-11-12"])

    def test_future_dates_never_receive_work_or_income_even_with_future_samples(self):
        rows = observations("2037-11-13T09:00", "2037-11-13T17:00")
        result = summarize(rows, SETTINGS, "today", stamp("2037-11-12T12:00"))
        future = [day for day in result["heatmap_recent_days"] if day["date"] > "2037-11-12"]
        self.assertTrue(future)
        for day in future:
            self.assertEqual(day["status"], "future")
            self.assertEqual(day["work_hours"], 0)
            self.assertEqual(day["observed_hours"], 0)
            self.assertEqual(day["income"], 0)
            self.assertIsNone(day["actual_rate"])
            self.assertIsNone(day["manual_kind"])

    def test_manual_and_sleep_sources_remain_visible_across_year(self):
        begin, end = stamp("2025-12-30T09:00"), stamp("2025-12-30T11:00")
        sleep = [{"start": begin, "end": end, "state": "connected", "last_sample_ts": begin - 5}]
        manual = [{"date": "2025-12-31", "kind": "daily_total", "hours": 11, "note": "estimated"}]
        result = summarize([], {**SETTINGS, "pause_on_sleep": False}, "today",
                           stamp("2026-01-05T12:00"), manual, sleep)
        days = {day["date"]: day for day in result["heatmap_recent_days"]}
        self.assertEqual(days["2025-12-30"]["source"], "sleep_estimate")
        self.assertEqual(days["2025-12-30"]["sleep_estimated_hours"], 2)
        self.assertEqual(days["2025-12-30"]["work_hours"], 2)
        self.assertEqual(days["2025-12-31"]["source"], "manual_estimate")
        self.assertEqual(days["2025-12-31"]["manual_note"], "estimated")
        self.assertEqual(days["2025-12-31"]["work_hours"], 11)


if __name__ == "__main__":
    unittest.main()
