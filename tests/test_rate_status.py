"""Actual rates use fixed pay per recorded date regardless of clock overlap."""

from copy import deepcopy
from datetime import datetime
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import summarize


ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {
    "annual_salary": 208800, "timezone": "America/Los_Angeles",
    "work_start": "09:00", "work_end": "17:00", "workdays": [0, 1, 2, 3, 4],
}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def observations(start, end, state="connected"):
    begin, finish = stamp(start), stamp(end)
    return [{"ts": ts, "state": state} for ts in range(int(begin), int(finish) + 1, 30)]


class RateStatusTests(unittest.TestCase):
    def test_after_hours_only_keeps_records_and_allocates_one_daily_salary(self):
        rows = observations("2037-11-12T18:00", "2037-11-12T18:07:30")
        original_rows, original_settings = deepcopy(rows), deepcopy(SETTINGS)
        result = summarize(rows, SETTINGS, "today", stamp("2037-11-12T18:08"))
        self.assertEqual(result["rate_status"], "ready")
        self.assertEqual(result["actual_rate"], 800)
        self.assertEqual(result["delta_percent"], 700)
        self.assertTrue(result["rate_floor_applied"])
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["recorded_days"], 1)
        self.assertEqual(result["work_hours"], 0.125)
        self.assertEqual(result["observed_hours"], 0.125)
        self.assertEqual(result["observed_scheduled_hours"], 0)
        self.assertEqual(result["coverage_percent"], 0)
        self.assertEqual(result["scheduled_hours"], 8)
        self.assertEqual(result["theoretical_rate"], 100)
        self.assertEqual(rows, original_rows)
        self.assertEqual(SETTINGS, original_settings)

    def test_daytime_coverage_plus_overtime_still_dilutes_rate(self):
        rows = observations("2026-11-12T09:00", "2026-11-12T19:00")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-12T20:00"))
        self.assertEqual(result["rate_status"], "ready")
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["work_hours"], 10)
        self.assertEqual(result["observed_scheduled_hours"], 8)
        self.assertEqual(result["actual_rate"], 80)
        self.assertAlmostEqual(result["delta_percent"], -20)

    def test_missing_salary_keeps_rate_unavailable_even_after_hours(self):
        rows = observations("2026-11-12T20:00", "2026-11-12T21:00")
        settings = {**SETTINGS, "annual_salary": None}
        for samples in [rows, []]:
            with self.subTest(samples=bool(samples)):
                result = summarize(samples, settings, "today", stamp("2026-11-12T21:00"))
                self.assertEqual(result["rate_status"], "missing_salary")
                self.assertIsNone(result["income"])
                self.assertIsNone(result["actual_rate"])
                self.assertIsNone(result["delta_percent"])

    def test_known_disconnected_day_earns_salary_without_dividing_by_zero(self):
        rows = observations("2026-11-12T09:00", "2026-11-12T10:00", "disconnected")
        for samples, expected_income in [([], 0), (rows, 800)]:
            with self.subTest(samples=bool(samples)):
                result = summarize(samples, SETTINGS, "today", stamp("2026-11-12T21:00"))
                self.assertEqual(result["rate_status"], "no_work")
                self.assertEqual(result["income"], expected_income)
                self.assertEqual(result["work_hours"], 0)
                self.assertIsNone(result["actual_rate"])
                self.assertIsNone(result["delta_percent"])

    def test_salary_history_and_after_hours_use_existing_daily_allocation(self):
        settings = {**SETTINGS, "salary_history": [
            {"effective_from": "2026-11-10", "annual_salary": 417600},
        ]}
        rows = observations("2026-11-09T09:00", "2026-11-09T10:00")
        rows += observations("2026-11-10T09:00", "2026-11-10T10:00")
        rows += observations("2026-11-10T20:00", "2026-11-10T21:00")
        result = summarize(rows, settings, "week", stamp("2026-11-10T21:00"))
        self.assertEqual(result["rate_status"], "ready")
        self.assertEqual(result["income"], 2400)
        self.assertEqual(result["work_hours"], 3)
        self.assertEqual(result["observed_scheduled_hours"], 2)
        self.assertEqual(result["actual_rate"], 800)
        self.assertEqual(result["theoretical_rate"], 200)
        self.assertEqual(result["delta_percent"], 300)

    def test_missing_historical_salary_keeps_precedence(self):
        settings = {**SETTINGS, "annual_salary": None, "salary_history": [
            {"effective_from": "2026-11-10", "annual_salary": 417600},
        ]}
        rows = observations("2026-11-09T09:00", "2026-11-09T10:00")
        rows += observations("2026-11-10T09:00", "2026-11-10T10:00")
        result = summarize(rows, settings, "week", stamp("2026-11-10T21:00"))
        self.assertEqual(result["rate_status"], "missing_salary")
        self.assertTrue(result["salary_incomplete"])
        self.assertIsNone(result["actual_rate"])
        self.assertIsNone(result["income"])


if __name__ == "__main__":
    unittest.main()
