"""Manual history changes totals without fabricating or duplicating VPN data."""

from copy import deepcopy
from datetime import datetime
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import summarize


ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {"annual_salary": 208800, "timezone": "America/Los_Angeles",
            "work_start": "09:00", "work_end": "17:00", "workdays": [0, 1, 2, 3, 4]}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def observations(start, end, state="connected"):
    return [{"ts": value, "state": state}
            for value in range(int(stamp(start)), int(stamp(end)) + 1, 30)]


def estimate(day, hours, note="按当时工作情况估算"):
    return {"date": day, "kind": "daily_total", "hours": hours, "note": note}


def intervals(day, *pairs, note="手动补记"):
    return {"date": day, "kind": "intervals",
            "intervals": [{"start": start, "end": end} for start, end in pairs], "note": note}


def by_date(summary):
    return {day["date"]: day for day in summary["days"]}


class ManualCoreTests(unittest.TestCase):
    def test_example_history_and_today_are_separate_from_raw_observations(self):
        manual = [estimate("2037-11-" + day, 11) for day in ["05", "06", "09", "10", "11"]]
        manual.append(intervals("2037-11-12", ("08:00", "15:00"), ("18:00", "20:00")))
        rows = observations("2037-11-12T19:40", "2037-11-12T19:44")
        before_rows, before_manual, before_settings = deepcopy(rows), deepcopy(manual), deepcopy(SETTINGS)
        result = summarize(rows, SETTINGS, "month", stamp("2037-11-12T19:45"), manual)
        self.assertEqual(result["work_hours"], 63.75)
        self.assertEqual(result["manual_days"], 6)
        self.assertEqual(result["recorded_days"], 6)
        self.assertEqual(result["estimated_hours"], 55)
        self.assertEqual(result["income"], 4800)
        days = by_date(result)
        self.assertEqual(days["2037-11-12"]["work_hours"], 8.75)
        self.assertAlmostEqual(days["2037-11-12"]["vpn_work_hours"], 4 / 60)
        self.assertEqual(days["2037-11-12"]["source"], "manual")
        self.assertEqual(days["2037-11-11"]["work_hours"], 11)
        self.assertEqual(days["2037-11-11"]["source"], "manual_estimate")
        self.assertEqual(days["2037-11-11"]["observed_hours"], 0)
        self.assertEqual(days["2037-11-11"]["manual_note"], "按当时工作情况估算")
        self.assertEqual(rows, before_rows)
        self.assertEqual(manual, before_manual)
        self.assertEqual(SETTINGS, before_settings)
        week = summarize(rows, SETTINGS, "week", stamp("2037-11-12T19:45"), manual)
        self.assertEqual(week["work_hours"], 41.75)
        self.assertEqual(week["estimated_hours"], 33)
        self.assertEqual(week["manual_days"], 4)

    def test_daily_total_overrides_instead_of_adding_and_removal_restores_vpn(self):
        rows = observations("2037-11-11T09:00", "2037-11-11T17:00")
        now = stamp("2037-11-12T20:45")
        baseline = summarize(rows, SETTINGS, "week", now)
        for hours in [3, 11]:
            with self.subTest(hours=hours):
                result = summarize(rows, SETTINGS, "week", now, [estimate("2037-11-11", hours)])
                day = by_date(result)["2037-11-11"]
                self.assertEqual(result["work_hours"], hours)
                self.assertEqual(day["vpn_work_hours"], 8)
                self.assertEqual(day["observed_hours"], 8)
                self.assertEqual(day["coverage_percent"], 100)
                self.assertEqual(day["manual_kind"], "daily_total")
                self.assertEqual(result["timeline"], baseline["timeline"])
                self.assertEqual(result["income"], 800)
        self.assertEqual(summarize(rows, SETTINGS, "week", now, []), baseline)

    def test_estimate_does_not_create_precise_time_intervals_or_observation_coverage(self):
        result = summarize([], SETTINGS, "week", stamp("2037-11-12T20:45"),
                           [estimate("2037-11-11", 11)])
        self.assertTrue(all(item["state"] == "unknown" and item["source"] == "vpn"
                            for item in result["timeline"]))
        self.assertEqual(result["observed_hours"], 0)
        self.assertEqual(result["observed_scheduled_hours"], 0)
        self.assertEqual(result["coverage_percent"], 0)
        self.assertEqual(result["manual_entries"], [estimate("2037-11-11", 11)])
        self.assertEqual(by_date(result)["2037-11-11"]["status"], "partial")

    def test_zero_hour_estimate_is_a_recorded_paid_day_without_division_by_zero(self):
        result = summarize([], SETTINGS, "week", stamp("2037-11-12T20:45"),
                           [estimate("2037-11-11", 0)])
        self.assertEqual(result["work_hours"], 0)
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["recorded_days"], 1)
        self.assertEqual(result["manual_days"], 1)
        self.assertIsNone(result["actual_rate"])
        self.assertEqual(by_date(result)["2037-11-11"]["rate_status"], "no_work")

    def test_manual_intervals_union_with_vpn_and_each_other(self):
        rows = observations("2037-11-11T10:00", "2037-11-11T12:00")
        rows += observations("2037-11-11T14:00", "2037-11-11T15:00")
        manual = [intervals("2037-11-11", ("11:00", "13:00"), ("09:00", "11:30"), ("09:00", "10:00"))]
        result = summarize(rows, SETTINGS, "week", stamp("2037-11-12T20:45"), manual)
        day = by_date(result)["2037-11-11"]
        self.assertEqual(result["work_hours"], 5)
        self.assertEqual(day["vpn_work_hours"], 3)
        self.assertEqual(day["observed_hours"], 5)
        self.assertEqual(result["estimated_hours"], 0)
        worked = [item for item in result["timeline"] if item["state"] == "connected"]
        self.assertEqual([(item["start"][11:16], item["end"][11:16], item["source"])
                          for item in worked], [("09:00", "13:00", "manual"), ("14:00", "15:00", "vpn")])

    def test_manual_interval_can_override_disconnected_status_without_double_coverage(self):
        rows = observations("2037-11-11T09:00", "2037-11-11T17:00", "disconnected")
        manual = [intervals("2037-11-11", ("09:00", "12:00"), ("13:00", "16:00"))]
        result = summarize(rows, SETTINGS, "week", stamp("2037-11-12T20:45"), manual)
        day = by_date(result)["2037-11-11"]
        self.assertEqual(day["work_hours"], 6)
        self.assertEqual(day["vpn_work_hours"], 0)
        self.assertEqual(day["observed_hours"], 8)
        self.assertEqual(day["coverage_percent"], 100)
        self.assertEqual(result["income"], 800)
        disconnected = [entry for entry in result["timeline"] if entry["state"] == "disconnected"]
        self.assertEqual([(entry["start"][11:16], entry["end"][11:16]) for entry in disconnected],
                         [("12:00", "13:00"), ("16:00", "17:00")])

    def test_today_intervals_clip_to_now_and_never_count_future_dates(self):
        manual = [intervals("2037-11-12", ("19:00", "21:00")),
                  intervals("2037-11-13", ("09:00", "17:00")), estimate("2037-11-14", 11)]
        now = stamp("2037-11-12T20:45")
        result = summarize([], SETTINGS, "today", now, manual)
        self.assertEqual(result["work_hours"], 1.75)
        self.assertEqual(result["manual_days"], 1)
        self.assertEqual(len(result["manual_entries"]), 1)
        self.assertTrue(all(datetime.fromisoformat(entry["end"]).timestamp() <= now
                            for entry in result["timeline"]))
        after_end = summarize([], SETTINGS, "today", stamp("2037-11-12T22:00"), manual)
        self.assertEqual(after_end["work_hours"], 2)
        before_start = summarize([], SETTINGS, "today", stamp("2037-11-12T18:00"), manual)
        self.assertEqual(before_start["work_hours"], 0)
        self.assertEqual(before_start["manual_days"], 0)
        self.assertEqual(before_start["manual_entries"], [])

    def test_today_daily_estimate_is_not_prematurely_applied(self):
        result = summarize([], SETTINGS, "today", stamp("2037-11-12T20:45"),
                           [estimate("2037-11-12", 11)])
        self.assertEqual(result["work_hours"], 0)
        self.assertEqual(result["income"], 0)
        self.assertEqual(result["manual_days"], 0)

    def test_salary_changes_and_weekends_apply_to_manual_dates(self):
        settings = {**SETTINGS, "salary_history": [{"effective_from": "2037-11-10", "annual_salary": 417600}]}
        manual = [estimate("2037-11-09", 11), estimate("2037-11-10", 11), estimate("2037-11-14", 11)]
        result = summarize([], settings, "month", stamp("2037-11-15T12:00"), manual)
        self.assertEqual(result["work_hours"], 33)
        self.assertEqual(result["income"], 2400)
        self.assertAlmostEqual(result["actual_rate"], 2400 / 33)
        days = by_date(result)
        self.assertEqual(days["2037-11-09"]["income"], 800)
        self.assertEqual(days["2037-11-10"]["income"], 1600)
        self.assertEqual(days["2037-11-14"]["income"], 0)
        self.assertEqual(days["2037-11-14"]["actual_rate"], 0)

    def test_manual_paid_date_still_requires_its_salary(self):
        settings = {**SETTINGS, "annual_salary": None}
        result = summarize([], settings, "week", stamp("2037-11-12T20:45"), [estimate("2037-11-11", 11)])
        self.assertEqual(result["work_hours"], 11)
        self.assertTrue(result["salary_incomplete"])
        self.assertIsNone(result["income"])
        self.assertEqual(by_date(result)["2037-11-11"]["rate_status"], "missing_salary")

    def test_rolling_boundary_daily_total_is_not_arbitrarily_time_prorated(self):
        manual = [estimate("2025-11-11", 11), estimate("2025-11-12", 11)]
        result = summarize([], SETTINGS, "rolling_year", stamp("2026-11-12T12:00"), manual)
        self.assertEqual(result["work_hours"], 11)
        self.assertEqual(result["manual_days"], 1)
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["manual_entries"], [estimate("2025-11-12", 11)])

    def test_24_hour_endpoint_uses_local_midnight_and_dst_elapsed_hours(self):
        settings = {**SETTINGS, "workdays": list(range(7))}
        for day, next_day, hours in [("2037-03-08", "2037-03-09", 23),
                                     ("2037-11-01", "2037-11-02", 25)]:
            with self.subTest(day=day):
                result = summarize([], settings, "month", stamp(next_day + "T00:00"),
                                   [intervals(day, ("00:00", "24:00"))])
                self.assertEqual(result["work_hours"], hours)
                self.assertEqual(result["recorded_days"], 1)
                self.assertEqual(result["manual_days"], 1)
                self.assertEqual(by_date(result)[next_day]["work_hours"], 0)

    def test_heatmap_manual_dates_are_independent_of_selected_period(self):
        result = summarize([], SETTINGS, "today", stamp("2037-11-12T20:45"),
                           [estimate("2037-11-05", 11)])
        self.assertEqual(result["work_hours"], 0)
        self.assertEqual(result["manual_days"], 0)
        self.assertEqual(by_date(result)["2037-11-05"]["work_hours"], 11)
        self.assertEqual(by_date(result)["2037-11-05"]["manual_kind"], "daily_total")


if __name__ == "__main__":
    unittest.main()
