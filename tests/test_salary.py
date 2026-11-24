"""Salary changes preserve the pay that applied on each observed local day."""

from datetime import datetime
import json
import pathlib
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import summarize
from store import Store, validate_settings


ZONE = ZoneInfo("America/Los_Angeles")
SETTINGS = {
    "annual_salary": 208800, "timezone": "America/Los_Angeles",
    "work_start": "09:00", "work_end": "17:00", "workdays": [0, 1, 2, 3, 4],
}


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


def observations(day, state="connected"):
    start = stamp(day + "T09:00")
    return [{"ts": start + offset, "state": state} for offset in range(0, 3601, 30)]


def change(day, salary):
    return {"effective_from": day, "annual_salary": salary}


class SalaryCalculationTests(unittest.TestCase):
    def test_old_single_salary_and_empty_history_have_identical_results(self):
        rows = observations("2026-11-09")
        now = stamp("2026-11-09T10:00")
        legacy = summarize(rows, SETTINGS, "today", now)
        self.assertEqual(legacy, summarize(rows, {**SETTINGS, "salary_history": []}, "today", now))
        self.assertEqual(legacy["current_annual_salary"], 208800)
        self.assertFalse(legacy["salary_incomplete"])
        self.assertEqual(legacy["actual_rate"], 800)

    def test_multiple_changes_apply_to_each_day_and_current_baseline(self):
        settings = {**SETTINGS, "salary_history": [change("2026-11-11", 626400), change("2026-11-10", 417600)]}
        rows = sum((observations(day) for day in ["2026-11-09", "2026-11-10", "2026-11-11"]), [])
        result = summarize(rows, settings, "week", stamp("2026-11-11T11:00"))
        self.assertEqual(result["income"], 4800)
        self.assertEqual(result["work_hours"], 3)
        self.assertEqual(result["actual_rate"], 1600)
        self.assertEqual(result["theoretical_rate"], 300)
        self.assertEqual(result["current_annual_salary"], 626400)

    def test_effective_date_is_inclusive_at_local_midnight(self):
        settings = {**SETTINGS, "salary_history": [change("2026-11-10", 417600)]}
        before = summarize([], settings, "today", stamp("2026-11-09T23:59:59"))
        after = summarize([], settings, "today", stamp("2026-11-10T00:00:00"))
        self.assertEqual(before["theoretical_rate"], 100)
        self.assertEqual(after["theoretical_rate"], 200)

    def test_future_salary_does_not_change_current_or_past_income(self):
        settings = {**SETTINGS, "salary_history": [change("2027-01-01", 417600)]}
        result = summarize(observations("2026-11-09"), settings, "today", stamp("2026-11-09T11:00"))
        self.assertEqual(result["income"], 800)
        self.assertEqual(result["theoretical_rate"], 100)
        self.assertEqual(result["current_annual_salary"], 208800)

    def test_cross_year_uses_salary_and_calendar_for_each_year(self):
        settings = {**SETTINGS, "annual_salary": 209600,
                    "salary_history": [change("2025-01-01", 417600)]}
        rows = observations("2024-12-31") + observations("2025-01-01")
        result = summarize(rows, settings, "rolling_year", stamp("2025-01-02T12:00"))
        # 2024 has 262 paid weekdays; 2025 has 261 paid weekdays.
        self.assertEqual(result["income"], 2400)
        self.assertEqual(result["actual_rate"], 1200)
        self.assertEqual(result["theoretical_rate"], 200)

    def test_missing_historical_salary_never_treats_that_work_as_free(self):
        settings = {**SETTINGS, "annual_salary": None,
                    "salary_history": [change("2026-11-10", 417600)]}
        rows = observations("2026-11-09") + observations("2026-11-10")
        result = summarize(rows, settings, "week", stamp("2026-11-10T11:00"))
        self.assertEqual(result["work_hours"], 2)
        self.assertTrue(result["salary_incomplete"])
        self.assertIsNone(result["income"])
        self.assertIsNone(result["actual_rate"])
        self.assertEqual(result["theoretical_rate"], 200)
        today = summarize(rows, settings, "today", stamp("2026-11-10T11:00"))
        self.assertFalse(today["salary_incomplete"])
        self.assertEqual(today["actual_rate"], 1600)

    def test_unpriced_disconnected_schedule_also_requires_salary(self):
        settings = {**SETTINGS, "annual_salary": None,
                    "salary_history": [change("2026-11-10", 417600)]}
        rows = observations("2026-11-09", "disconnected") + observations("2026-11-10")
        result = summarize(rows, settings, "week", stamp("2026-11-10T11:00"))
        self.assertEqual(result["work_hours"], 1)
        self.assertTrue(result["salary_incomplete"])
        self.assertIsNone(result["actual_rate"])

    def test_no_data_and_no_effective_salary_stays_unpriced(self):
        settings = {**SETTINGS, "annual_salary": None,
                    "salary_history": [change("2027-01-01", 417600)]}
        result = summarize([], settings, "today", stamp("2026-11-10T11:00"))
        self.assertIsNone(result["current_annual_salary"])
        self.assertIsNone(result["income"])
        self.assertIsNone(result["actual_rate"])
        self.assertFalse(result["salary_incomplete"])

    def test_unknown_observation_gap_does_not_require_salary(self):
        settings = {**SETTINGS, "annual_salary": None,
                    "salary_history": [change("2026-11-10", 417600)]}
        rows = observations("2026-11-09", "unknown") + observations("2026-11-10")
        result = summarize(rows, settings, "week", stamp("2026-11-10T11:00"))
        self.assertFalse(result["salary_incomplete"])
        self.assertEqual(result["income"], 1600)


class SalarySettingsTests(unittest.TestCase):
    def test_history_normalizes_order_without_mutating_caller(self):
        history = [change("2026-11-10", 417600), change("2026-01-01", 208800)]
        settings = validate_settings({"salary_history": history})
        self.assertEqual(settings["salary_history"], list(reversed(history)))
        settings["salary_history"][0]["annual_salary"] = 999
        self.assertEqual(history[1]["annual_salary"], 208800)

    def test_invalid_dates_duplicate_days_and_amounts_are_rejected(self):
        invalid = [None, {}, [None], ["2026-01-01"],
                   [{"effective_from": "2026-01-01"}],
                   [{**change("2026-01-01", 100), "end": "2026-02-01"}],
                   [change("2026-01-01", 100), change("2026-01-01", 200)]]
        invalid += [[change(day, 100)] for day in
                    [None, True, "2026-02-29", "20261110", "2026-W02-1", "2026-1-1", "2026-11-10T00:00:00"]]
        invalid += [[change("2026-01-01", salary)] for salary in
                    [None, True, "100", 0, -1, float("nan"), float("inf"), 1e11, 10 ** 1000]]
        for history in invalid:
            with self.subTest(history=history):
                with self.assertRaises(ValueError):
                    validate_settings({"salary_history": history})
                with self.assertRaises(ValueError):
                    summarize([], {**SETTINGS, "salary_history": history})

    def test_history_and_observations_survive_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            expected = [change("2026-01-01", 208800), change("2026-11-10", 417600)]
            try:
                store.save_settings({"annual_salary": 100000, "salary_history": expected})
                store.record(stamp("2026-11-09T09:00"), "connected")
                store.sync()
            finally:
                store.close()
            store = Store(directory)
            try:
                self.assertEqual(store.settings()["salary_history"], expected)
                self.assertEqual(store.settings()["annual_salary"], 100000)
                self.assertEqual(len(store.published_samples()), 1)
                store.save_settings({"currency": "CNY"})
                self.assertEqual(store.settings()["salary_history"], expected)
                with self.assertRaises(ValueError):
                    store.save_settings({"salary_history": [change("bad", 100)]})
                self.assertEqual(store.settings()["salary_history"], expected)
            finally:
                store.close()

    def test_existing_settings_without_history_keep_original_salary(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                legacy = validate_settings({"annual_salary": 123456})
                legacy.pop("salary_history")
                store.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("settings", json.dumps(legacy)))
                store.db.commit()
            finally:
                store.close()
            store = Store(directory)
            try:
                self.assertEqual(store.settings()["annual_salary"], 123456)
                self.assertEqual(store.settings()["salary_history"], [])
                store.save_settings({"salary_history": [change("2026-11-10", 234567)]})
                self.assertEqual(store.settings()["annual_salary"], 123456)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
