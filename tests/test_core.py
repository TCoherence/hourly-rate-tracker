"""Daily salary accounting, unknown observation gaps, and local dates."""

import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import summarize


ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {
    "annual_salary": 208800,
    "currency": "USD",
    "timezone": "America/Los_Angeles",
    "work_start": "09:00",
    "work_end": "17:00",
    "workdays": [0, 1, 2, 3, 4],
}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def observations(start, end, state="connected", step=30):
    begin = stamp(start) if isinstance(start, str) else start
    finish = stamp(end) if isinstance(end, str) else end
    result = []
    while begin < finish:
        result.append({"ts": begin, "state": state})
        begin += step
    result.append({"ts": finish, "state": state})
    return result


class CoreTests(unittest.TestCase):
    def test_normal_workday_matches_theoretical_and_only_observed_income(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T17:00")
        result = summarize(rows, SETTINGS, "year", stamp("2026-11-09T18:00"))
        self.assertAlmostEqual(result["theoretical_rate"], 100)
        self.assertAlmostEqual(result["income"], 800)
        self.assertAlmostEqual(result["work_hours"], 8)
        self.assertAlmostEqual(result["actual_rate"], 100)
        self.assertLess(result["coverage_percent"], 1)
        self.assertGreater(result["scheduled_hours"], 1000)

    def test_overtime_dilutes_rate_and_disconnected_time_is_covered(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T19:00")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-09T20:00"))
        self.assertAlmostEqual(result["income"], 800)
        self.assertAlmostEqual(result["work_hours"], 10)
        self.assertAlmostEqual(result["actual_rate"], 80)
        self.assertAlmostEqual(result["delta_percent"], -20)
        self.assertEqual(result["coverage_percent"], 100)

        rows = observations("2026-11-09T09:00", "2026-11-09T13:00")
        rows += observations("2026-11-09T13:00", "2026-11-09T17:00", "disconnected")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-09T18:00"))
        self.assertAlmostEqual(result["work_hours"], 4)
        self.assertAlmostEqual(result["observed_hours"], 8)
        self.assertAlmostEqual(result["income"], 800)
        self.assertAlmostEqual(result["actual_rate"], 200)

    def test_long_gap_is_unknown_and_no_tail_extrapolation(self):
        rows = [
            {"ts": stamp("2026-11-09T09:00"), "state": "connected"},
            {"ts": stamp("2026-11-09T09:00:30"), "state": "connected"},
            {"ts": stamp("2026-11-09T16:00"), "state": "connected"},
        ]
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-09T17:00"))
        self.assertAlmostEqual(result["work_hours"], 30 / 3600)
        self.assertAlmostEqual(result["income"], 800)
        self.assertEqual(result["recorded_days"], 1)
        self.assertEqual(result["timeline"][-1]["state"], "unknown")

    def test_no_samples_and_zero_connected_never_produce_infinity(self):
        result = summarize([], SETTINGS, "today", stamp("2026-11-09T17:00"))
        self.assertIsNone(result["actual_rate"])
        self.assertEqual(result["income"], 0)
        self.assertEqual(result["coverage_percent"], 0)
        self.assertEqual(result["timeline"][0]["state"], "unknown")
        rows = observations("2026-11-09T09:00", "2026-11-09T17:00", "disconnected")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-09T18:00"))
        self.assertIsNone(result["actual_rate"])
        self.assertIsNone(result["delta_percent"])
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["work_hours"], 0)
        self.assertFalse(result["rate_floor_applied"])

    def test_minimum_one_hour_applies_to_daily_rates_only(self):
        start = stamp("2026-11-09T09:00")
        for seconds, expected, floored in [(30, 800, True), (1800, 800, True),
                                            (3600, 800, False), (5400, 800 / 1.5, False)]:
            with self.subTest(seconds=seconds):
                rows = observations(start, start + seconds)
                today = summarize(rows, SETTINGS, "today", start + seconds)
                week = summarize(rows, SETTINGS, "week", start + seconds)
                self.assertAlmostEqual(today["work_hours"], seconds / 3600)
                self.assertAlmostEqual(today["actual_rate"], expected)
                self.assertEqual(today["rate_floor_applied"], floored)
                for key in ("period_days", "days", "heatmap_recent_days"):
                    day = next(d for d in today[key] if d["date"] == "2026-11-09")
                    self.assertAlmostEqual(day["work_hours"], seconds / 3600)
                    self.assertAlmostEqual(day["actual_rate"], expected)
                    self.assertEqual(day["rate_floor_applied"], floored)
                self.assertAlmostEqual(week["actual_rate"], 800 / (seconds / 3600))
                self.assertFalse(week["rate_floor_applied"])

        missing = summarize(observations(start, start + 30),
                            {**SETTINGS, "annual_salary": None}, "today", start + 30)
        self.assertIsNone(missing["actual_rate"])
        self.assertFalse(missing["rate_floor_applied"])

    def test_salary_not_entered_keeps_activity_and_null_rates(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T10:00")
        result = summarize(rows, {**SETTINGS, "annual_salary": None}, "today", stamp("2026-11-09T10:00"))
        self.assertEqual(result["work_hours"], 1)
        self.assertIsNone(result["actual_rate"])
        self.assertIsNone(result["theoretical_rate"])
        self.assertIsNone(result["income"])

    def test_duplicates_unsorted_rows_and_unknown_states_do_not_double_count(self):
        first = stamp("2026-11-09T09:00")
        rows = [
            {"ts": first + 30, "state": "connected"},
            {"ts": first, "state": "disconnected"},
            {"ts": first, "state": "connected"},
            {"ts": first + 60, "state": "not-a-status"},
            {"ts": first + 90, "state": "connected"},
            {"ts": "bad", "state": "connected"},
            {"ts": float("nan"), "state": "connected"},
        ]
        result = summarize(rows, SETTINGS, "today", first + 90)
        self.assertEqual(result["work_hours"], 60 / 3600)
        self.assertEqual(result["observed_hours"], 60 / 3600)

    def test_future_observations_are_ignored(self):
        rows = observations("2026-11-09T09:00", "2026-11-09T10:00")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-09T09:30"))
        self.assertEqual(result["work_hours"], 0.5)
        self.assertEqual(result["income"], 800)

    def test_local_midnight_split(self):
        rows = observations("2026-11-08T23:30", "2026-11-09T00:30")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-09T01:00"))
        self.assertEqual(result["work_hours"], 0.5)
        days = {day["date"]: day for day in result["days"]}
        self.assertEqual(days["2026-11-08"]["work_hours"], 0.5)
        self.assertEqual(days["2026-11-09"]["work_hours"], 0.5)
        self.assertEqual(days["2026-11-08"]["income"], 0)
        self.assertEqual(days["2026-11-08"]["actual_rate"], 0)
        self.assertEqual(days["2026-11-09"]["income"], 800)
        self.assertEqual(days["2026-11-09"]["actual_rate"], 800)
        self.assertTrue(days["2026-11-09"]["rate_floor_applied"])
        self.assertEqual(result["recorded_days"], 1)
        self.assertEqual(days["2026-11-10"]["status"], "future")
        self.assertEqual(days["2026-11-07"]["status"], "unknown")
        self.assertEqual(days["2026-11-07"]["income"], 0)
        self.assertEqual(days["2026-11-07"]["rate_status"], "no_records")

    def test_dst_uses_elapsed_seconds_not_wall_clock_subtraction(self):
        settings = {**SETTINGS, "workdays": list(range(7)), "work_start": "00:00", "work_end": "04:00",
                    "theoretical_daily_hours": 4}
        for day, expected_hours in [("2026-03-08", 3), ("2026-11-01", 5)]:
            begin = stamp(day + "T00:00")
            end = stamp(day + "T04:00")
            rows = observations(begin, end)
            result = summarize(rows, settings, "today", end)
            self.assertEqual(result["work_hours"], expected_hours)
            self.assertEqual(result["scheduled_hours"], expected_hours)
            self.assertAlmostEqual(result["income"], SETTINGS["annual_salary"] / 365)
            self.assertAlmostEqual(result["actual_rate"], SETTINGS["annual_salary"] / 365 / expected_hours)
            self.assertAlmostEqual(result["theoretical_rate"], SETTINGS["annual_salary"] / 365 / 4)

    def test_theoretical_hours_are_independent_of_clock_schedule_and_daily_pay(self):
        rows = observations("2026-11-12T20:00", "2026-11-12T21:00")
        settings = {**SETTINGS, "theoretical_daily_hours": 6,
                    "work_start": "10:00", "work_end": "11:00"}
        result = summarize(rows, settings, "today", stamp("2026-11-12T21:00"))
        self.assertAlmostEqual(result["theoretical_rate"], 800 / 6)
        self.assertEqual(result["theoretical_daily_hours"], 6)
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["actual_rate"], 800)
        self.assertEqual(result["observed_scheduled_hours"], 0)
        default = summarize(rows, {**settings, "theoretical_daily_hours": 8}, "today", stamp("2026-11-12T21:00"))
        self.assertEqual(default["theoretical_rate"], 100)
        self.assertEqual(default["income"], result["income"])
        self.assertEqual(default["actual_rate"], result["actual_rate"])

    def test_multiple_days_include_disconnected_days_but_not_unknown_days(self):
        rows = observations("2026-11-09T20:00", "2026-11-09T21:00")
        rows += observations("2026-11-10T20:00", "2026-11-10T21:00", "disconnected")
        rows += observations("2026-11-11T09:00", "2026-11-11T15:00", "unknown")
        rows += observations("2026-11-12T20:00", "2026-11-12T22:00")
        result = summarize(rows, SETTINGS, "week", stamp("2026-11-12T22:00"))
        self.assertEqual(result["recorded_days"], 3)
        self.assertEqual(result["income"], 2400)
        self.assertEqual(result["work_hours"], 3)
        self.assertEqual(result["actual_rate"], 800)
        days = {day["date"]: day for day in result["days"]}
        self.assertEqual(days["2026-11-10"]["income"], 800)
        self.assertIsNone(days["2026-11-10"]["actual_rate"])
        self.assertEqual(days["2026-11-10"]["rate_status"], "no_work")
        self.assertEqual(days["2026-11-11"]["income"], 0)
        self.assertEqual(days["2026-11-11"]["rate_status"], "no_records")

    def test_midnight_endpoint_does_not_credit_an_unobserved_second_day(self):
        rows = observations("2026-11-09T23:59:30", "2026-11-10T00:00")
        result = summarize(rows, SETTINGS, "week", stamp("2026-11-10T01:00"))
        self.assertEqual(result["recorded_days"], 1)
        self.assertEqual(result["income"], 800)
        days = {day["date"]: day for day in result["days"]}
        self.assertEqual(days["2026-11-10"]["income"], 0)
        self.assertEqual(days["2026-11-10"]["rate_status"], "no_records")
        point_only = summarize(rows[-1:], SETTINGS, "today", stamp("2026-11-10T01:00"))
        self.assertEqual(point_only["recorded_days"], 0)
        self.assertEqual(point_only["income"], 0)

    def test_weekend_work_adds_hours_without_additional_fixed_income(self):
        weekend = observations("2026-11-14T14:00", "2026-11-14T16:00")
        rows = observations("2026-11-13T09:00", "2026-11-13T17:00") + weekend
        result = summarize(rows, SETTINGS, "week", stamp("2026-11-14T18:00"))
        self.assertEqual(result["recorded_days"], 2)
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["work_hours"], 10)
        self.assertEqual(result["actual_rate"], 80)
        today = summarize(weekend, SETTINGS, "today", stamp("2026-11-14T18:00"))
        self.assertEqual(today["income"], 0)
        self.assertEqual(today["actual_rate"], 0)
        self.assertEqual(today["rate_status"], "ready")

    def test_rolling_window_boundary_date_gets_one_daily_salary(self):
        rows = observations("2025-11-12T11:30", "2025-11-12T12:30")
        result = summarize(rows, SETTINGS, "rolling_year", stamp("2026-11-12T12:00"))
        self.assertEqual(result["recorded_days"], 1)
        self.assertEqual(result["work_hours"], 0.5)
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["actual_rate"], 1600)

    def test_period_starts_monday_quarter_half_and_year(self):
        now = stamp("2026-11-10T12:00")
        expected = {
            "today": "2026-11-10T00:00:00-08:00",
            "week": "2026-11-09T00:00:00-08:00",
            "month": "2026-11-01T00:00:00-07:00",
            "quarter": "2026-10-01T00:00:00-07:00",
            "half": "2026-07-01T00:00:00-07:00",
            "year": "2026-01-01T00:00:00-08:00",
        }
        for period, start in expected.items():
            self.assertEqual(summarize([], SETTINGS, period, now)["start"], start)
        rolling = summarize([], SETTINGS, "rolling_year", now)
        self.assertEqual(datetime.fromisoformat(rolling["end"]).timestamp() - datetime.fromisoformat(rolling["start"]).timestamp(), 365 * 86400)

    def test_rolling_year_uses_each_year_salary_denominator(self):
        rows = observations("2024-11-11T09:00", "2024-11-11T17:00")
        rows += observations("2025-11-07T09:00", "2025-11-07T17:00")
        result = summarize(rows, SETTINGS, "rolling_year", stamp("2025-11-10T08:00"))
        self.assertEqual(result["work_hours"], 16)
        # 2024 has 262 Monday–Friday days; 2025 has 261.
        self.assertAlmostEqual(result["income"], SETTINGS["annual_salary"] / 262 + SETTINGS["annual_salary"] / 261)

    def test_leap_year_heatmap_has_february_29(self):
        result = summarize([], SETTINGS, "year", stamp("2024-11-10T12:00"))
        self.assertEqual(len(result["days"]), 366)
        self.assertIn("2024-02-29", {day["date"] for day in result["days"]})

    def test_heatmap_uses_current_year_independent_of_selected_period(self):
        rows = observations("2026-01-05T09:00", "2026-01-05T17:00")
        result = summarize(rows, SETTINGS, "today", stamp("2026-11-10T12:00"))
        self.assertEqual(result["work_hours"], 0)
        days = {day["date"]: day for day in result["days"]}
        self.assertEqual(days["2026-01-05"]["work_hours"], 8)
        self.assertEqual(days["2026-01-05"]["coverage_percent"], 100)
        self.assertEqual(days["2026-01-05"]["status"], "partial")
        self.assertEqual(len(result["days"]), 365)

    def test_input_validation(self):
        for settings in [
            {**SETTINGS, "annual_salary": -1},
            {**SETTINGS, "annual_salary": float("inf")},
            {**SETTINGS, "workdays": []},
            {**SETTINGS, "workdays": [7]},
            {**SETTINGS, "work_start": "17:00", "work_end": "09:00"},
            *({**SETTINGS, "theoretical_daily_hours": value}
              for value in [None, True, "8", 0, -1, 25, float("nan"), float("inf"), 10 ** 1000]),
        ]:
            with self.assertRaises(ValueError):
                summarize([], settings)
        with self.assertRaises(ValueError):
            summarize([], SETTINGS, "invalid-period")


if __name__ == "__main__":
    unittest.main()
