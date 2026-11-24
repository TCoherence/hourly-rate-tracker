"""Previous-period rates reuse the same accounting and local-date rules."""
from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import summarize

ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {"annual_salary": 260000, "timezone": str(ZONE), "workdays": [0, 1, 2, 3, 4]}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def samples(day, start=9, hours=8):
    begin = stamp(f"{day}T{start:02}:00")
    return [{"ts": begin + n, "state": "connected"} for n in range(0, hours * 3600 + 1, 30)]


class PreviousPeriodComparisonTests(unittest.TestCase):
    def test_today_comparison_uses_daily_floor_for_both_workdays(self):
        previous = stamp("2037-04-10T09:00")
        current = stamp("2037-04-13T09:00")
        rows = [{"ts": previous + offset, "state": "connected"} for offset in range(0, 1801, 30)]
        rows += [{"ts": current + offset, "state": "connected"} for offset in range(0, 901, 30)]
        result = summarize(rows, SETTINGS, "today", current + 900)
        comparison = result["period_comparison"]
        self.assertTrue(result["rate_floor_applied"])
        self.assertTrue(comparison["rate_floor_applied"])
        self.assertEqual(comparison["delta_percent"], 0)
        self.assertEqual(result["actual_rate"], comparison["actual_rate"])

        # Weekly comparisons still use each complete period's real hours.
        week = summarize(rows, SETTINGS, "week", current + 900)
        self.assertFalse(week["rate_floor_applied"])
        self.assertFalse(week["period_comparison"]["rate_floor_applied"])
        self.assertAlmostEqual(week["period_comparison"]["delta_percent"], 100)

    def test_today_compares_previous_configured_workday_not_nearest_record(self):
        rows = samples("2037-04-10", hours=10) + samples("2037-04-13", hours=8)
        result = summarize(rows, SETTINGS, "today", stamp("2037-04-13T18:00"))
        comparison = result["period_comparison"]
        self.assertEqual((comparison["start"], comparison["end_exclusive"]), ("2037-04-10", "2037-04-11"))
        self.assertEqual(comparison["label"], "上一个工作日")
        self.assertAlmostEqual(comparison["delta_percent"], 25)
        self.assertAlmostEqual(result["actual_rate"] / comparison["actual_rate"], 1.25)
        # A missing Friday is not silently replaced by an older Thursday.
        rows = samples("2037-04-09") + samples("2037-04-13")
        comparison = summarize(rows, SETTINGS, "today", stamp("2037-04-13T18:00"))["period_comparison"]
        self.assertEqual(comparison["rate_status"], "no_records")
        self.assertIsNone(comparison["delta_percent"])

    def test_week_compares_whole_previous_week_including_weekend(self):
        rows = samples("2037-04-06") + samples("2037-04-07") + samples("2037-04-11", hours=4)
        rows += samples("2037-04-13", hours=4)
        comparison = summarize(rows, SETTINGS, "week", stamp("2037-04-13T15:00"))["period_comparison"]
        self.assertEqual((comparison["start"], comparison["end_exclusive"]), ("2037-04-06", "2037-04-13"))
        self.assertEqual(comparison["label"], "上周")
        self.assertEqual(comparison["recorded_days"], 3)
        # Previous period has two weekdays' income over 20 hours, versus one over four.
        self.assertAlmostEqual(comparison["delta_percent"], 150)

    def test_month_uses_previous_calendar_month_and_effective_salary(self):
        rows = samples("2037-04-30") + samples("2037-05-04")
        settings = {**SETTINGS, "salary_history": [{"effective_from": "2037-05-01", "annual_salary": 520000}]}
        comparison = summarize(rows, settings, "month", stamp("2037-05-04T18:00"))["period_comparison"]
        self.assertEqual((comparison["start"], comparison["end_exclusive"]), ("2037-04-01", "2037-05-01"))
        self.assertAlmostEqual(comparison["delta_percent"], 100)

    def test_missing_salary_and_no_work_are_not_zero_rates(self):
        rows = samples("2037-04-10") + samples("2037-04-13")
        settings = {**SETTINGS, "annual_salary": None,
                    "salary_history": [{"effective_from": "2037-04-13", "annual_salary": 260000}]}
        comparison = summarize(rows, settings, "today", stamp("2037-04-13T18:00"))["period_comparison"]
        self.assertEqual(comparison["rate_status"], "missing_salary")
        self.assertIsNone(comparison["actual_rate"])
        self.assertIsNone(comparison["delta_percent"])
        manual = [{"date": "2037-04-10", "kind": "daily_total", "hours": 0}]
        comparison = summarize(samples("2037-04-13"), SETTINGS, "today", stamp("2037-04-13T18:00"), manual)["period_comparison"]
        self.assertEqual(comparison["rate_status"], "no_work")
        self.assertIsNone(comparison["actual_rate"])

    def test_zero_previous_rate_does_not_divide_by_zero(self):
        rows = samples("2037-04-11", hours=4) + samples("2037-04-13", hours=4)
        comparison = summarize(rows, SETTINGS, "week", stamp("2037-04-13T15:00"))["period_comparison"]
        self.assertEqual(comparison["rate_status"], "ready")
        self.assertEqual(comparison["actual_rate"], 0)
        self.assertIsNone(comparison["delta_percent"])

    def test_no_comparison_for_unrequested_ranges(self):
        for period in ("quarter", "half", "year", "rolling_year"):
            self.assertIsNone(summarize([], SETTINGS, period, stamp("2037-04-13T12:00"))["period_comparison"])

    def test_manual_override_and_pause_apply_to_previous_period(self):
        rows = samples("2037-04-10", hours=8) + samples("2037-04-13", hours=4)
        settings = {**SETTINGS, "manual_pauses": [{"start":stamp("2037-04-10T10:00"), "end":stamp("2037-04-10T12:00")}]}
        manual = [{"date":"2037-04-10", "kind":"intervals", "intervals":[{"start":"10:00", "end":"11:00"}], "note":""}]
        comparison = summarize(rows, settings, "today", stamp("2037-04-13T15:00"), manual)["period_comparison"]
        self.assertAlmostEqual(comparison["delta_percent"], 75)

    def test_week_crossing_dst_keeps_local_monday_boundaries(self):
        # In Los Angeles, 2037-03-08 is the spring-forward Sunday.
        rows = samples("2037-03-06") + samples("2037-03-08", hours=4)
        rows += samples("2037-03-09", hours=4)
        comparison = summarize(rows, SETTINGS, "week", stamp("2037-03-09T15:00"))["period_comparison"]
        self.assertEqual((comparison["start"], comparison["end_exclusive"]), ("2037-03-02", "2037-03-09"))
        # Previous Friday's daily salary over 12 hours vs Monday's over 4.
        self.assertAlmostEqual(comparison["delta_percent"], 200)

    def test_previous_workday_crossing_year_uses_that_years_workday_count(self):
        rows = samples("2036-12-31") + samples("2037-01-02")
        result = summarize(rows, SETTINGS, "today", stamp("2037-01-02T18:00"))
        comparison = result["period_comparison"]
        self.assertEqual(comparison["start"], "2037-01-01")  # New Year's Day is not specially excluded.
        self.assertIsNone(comparison["actual_rate"])
        self.assertEqual(comparison["rate_status"], "no_records")

        # With Thursday configured as a non-workday, Wednesday 2036 is the prior working day.
        rows = samples("2036-12-31") + samples("2037-01-02")
        settings = {**SETTINGS, "workdays": [0, 1, 2, 4]}
        comparison = summarize(rows, settings, "today", stamp("2037-01-02T18:00"))["period_comparison"]
        self.assertEqual(comparison["start"], "2036-12-31")
        self.assertEqual(comparison["rate_status"], "ready")
        self.assertGreater(comparison["actual_rate"], 0)


if __name__ == "__main__":
    unittest.main()
