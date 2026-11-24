"""Daily chart data uses the selected window, including previous-year dates."""

from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import summarize

ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {"annual_salary": 208800, "timezone": str(ZONE),
            "workdays": [0, 1, 2, 3, 4]}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def observations(begin, end, state="connected"):
    start, stop = stamp(begin), stamp(end)
    return [{"ts": ts, "state": state} for ts in range(int(start), int(stop) + 1, 30)]


class PeriodDaysTests(unittest.TestCase):
    def assert_totals_match(self, result):
        self.assertAlmostEqual(sum(day["work_hours"] for day in result["period_days"]), result["work_hours"])
        self.assertAlmostEqual(sum(day["income"] for day in result["period_days"]), result["income"])

    def test_today_has_one_point_and_remains_partial_even_if_observed_since_midnight(self):
        rows = observations("2026-11-12T00:00", "2026-11-12T01:00")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-12T01:00"))
        self.assertEqual(len(result["period_days"]), 1)
        day = result["period_days"][0]
        self.assertEqual(day["date"], "2026-11-12")
        self.assertEqual(day["work_hours"], 1)
        self.assertEqual(day["actual_rate"], 800)
        self.assertEqual(day["status"], "partial")
        self.assertTrue(day["partial_day"])
        # The independent full-year heatmap retains its existing semantics.
        self.assertEqual(next(d for d in result["days"] if d["date"] == day["date"])["status"], "observed")
        self.assert_totals_match(result)

    def test_unknown_days_are_distinct_from_disconnected_and_manual_zero_days(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T10:00")
        rows += observations("2026-11-11T09:00", "2026-11-11T10:00", "disconnected")
        manual = [{"date": "2026-11-10", "kind": "daily_total", "hours": 0}]
        result = summarize(rows, SETTINGS, "week", stamp("2026-11-12T12:00"), manual)
        days = {d["date"]: d for d in result["period_days"]}
        self.assertEqual(list(days), ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"])
        for date in ("2026-11-10", "2026-11-11"):
            self.assertEqual(days[date]["work_hours"], 0)
            self.assertEqual(days[date]["rate_status"], "no_work")
            self.assertNotEqual(days[date]["status"], "unknown")
            self.assertIsNone(days[date]["actual_rate"])
        self.assertEqual(days["2026-11-12"]["status"], "unknown")
        self.assertEqual(days["2026-11-12"]["rate_status"], "no_records")
        self.assert_totals_match(result)

    def test_rolling_year_includes_previous_year_and_clips_both_boundary_dates(self):
        rows = observations("2025-11-12T11:00", "2025-11-12T13:00")
        rows += observations("2026-11-12T11:00", "2026-11-12T13:00")
        result = summarize(rows, SETTINGS, "rolling_year", stamp("2026-11-12T12:00"))
        days = result["period_days"]
        self.assertEqual((days[0]["date"], days[-1]["date"]), ("2025-11-12", "2026-11-12"))
        self.assertEqual(len(days), 366)
        self.assertEqual(days[0]["work_hours"], 1)
        self.assertEqual(days[-1]["work_hours"], 1)
        self.assertTrue(days[0]["partial_day"])
        self.assertTrue(days[-1]["partial_day"])
        self.assertTrue(all(d["status"] == "unknown" for d in days[1:-1]))
        self.assertTrue(all(d["date"].startswith("2026-") for d in result["days"]))
        self.assert_totals_match(result)

    def test_daily_rates_follow_salary_effective_dates_instead_of_period_average(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T17:00")
        rows += observations("2026-11-10T09:00", "2026-11-10T17:00")
        settings = {**SETTINGS, "salary_history": [{"effective_from": "2026-11-10", "annual_salary": 417600}]}
        result = summarize(rows, settings, "week", stamp("2026-11-10T18:00"))
        self.assertEqual([d["actual_rate"] for d in result["period_days"]], [100, 200])
        self.assertEqual(result["actual_rate"], 150)
        self.assert_totals_match(result)

    def test_missing_salary_preserves_hours_without_fabricating_zero_hourly_rate(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T17:00")
        result = summarize(rows, {**SETTINGS, "annual_salary": None}, "week", stamp("2026-11-10T12:00"))
        day = result["period_days"][0]
        self.assertEqual(day["work_hours"], 8)
        self.assertEqual(day["rate_status"], "missing_salary")
        self.assertIsNone(day["actual_rate"])
        self.assertIsNone(day["income"])
        self.assertEqual(result["period_days"][1]["rate_status"], "no_records")

    def test_sleep_and_manual_sources_match_combined_metrics_without_duplicate_hours(self):
        begin, end = stamp("2026-11-11T09:00"), stamp("2026-11-11T11:00")
        sleep = [{"start": begin, "end": end, "state": "connected", "last_sample_ts": begin - 5}]
        manual = [{"date": "2026-11-11", "kind": "intervals", "note": "test",
                   "intervals": [{"start": "10:00", "end": "12:00"}]}]
        settings = {**SETTINGS, "pause_on_sleep": False}
        result = summarize([], settings, "week", stamp("2026-11-12T12:00"), manual, sleep)
        day = next(d for d in result["period_days"] if d["date"] == "2026-11-11")
        self.assertEqual(day["work_hours"], 3)
        self.assertEqual(day["sleep_estimated_hours"], 1)
        self.assertEqual(day["source"], "manual")
        self.assert_totals_match(result)
        manual = [{"date": "2026-11-11", "kind": "daily_total", "hours": 4}]
        result = summarize([], settings, "week", stamp("2026-11-12T12:00"), manual, sleep)
        day = next(d for d in result["period_days"] if d["date"] == "2026-11-11")
        self.assertEqual(day["work_hours"], 4)
        self.assertEqual(day["sleep_estimated_hours"], 0)
        self.assertEqual(day["source"], "manual_estimate")
        self.assert_totals_match(result)

    def test_dst_dates_use_elapsed_hours_and_calendar_date_axis(self):
        manual = [{"date": "2026-11-01", "kind": "intervals",
                   "intervals": [{"start": "00:00", "end": "24:00"}]}]
        result = summarize([], SETTINGS, "month", stamp("2026-11-02T00:00"), manual)
        self.assertEqual([d["date"] for d in result["period_days"]], ["2026-11-01", "2026-11-02"])
        self.assertEqual(result["period_days"][0]["work_hours"], 25)
        self.assertEqual(result["period_days"][0]["actual_rate"], 0)  # Sunday adds hours, no salary.
        self.assertEqual(result["period_days"][1]["status"], "unknown")
        self.assert_totals_match(result)

    def test_boundary_manual_daily_total_matches_existing_non_prorated_policy(self):
        manual = [{"date": "2025-11-12", "kind": "daily_total", "hours": 11}]
        result = summarize([], SETTINGS, "rolling_year", stamp("2026-11-12T12:00"), manual)
        day = result["period_days"][0]
        self.assertEqual(day["date"], "2025-11-12")
        self.assertEqual(day["work_hours"], 11)
        self.assertTrue(day["partial_day"])
        self.assertEqual(day["manual_kind"], "daily_total")
        self.assert_totals_match(result)


if __name__ == "__main__":
    unittest.main()
