"""Portable local exports; never read credentials or contact a remote service."""
from bisect import bisect_left, bisect_right
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import math
from zoneinfo import ZoneInfo

from core import calendar_month

MAX_RESTORE_BYTES = 128 * 1024 * 1024
# Leave room for request wrapping and JSON re-serialization in the browser.
MAX_BACKUP_BYTES = 112 * 1024 * 1024


class BackupTooLarge(ValueError):
    pass


def json_backup(snapshot, now):
    """Versioned, lossless application data snapshot (including pending samples)."""
    return {"format": "hourly-rate-backup", "version": 1,
            "exported_at": datetime.fromtimestamp(now, timezone.utc).isoformat(), **snapshot}


def serialize_backup(snapshot, now):
    """Never produce a backup that this version's restore rejects."""
    payload = json_backup(snapshot, now)
    if any(len(payload[name]) > 3_000_000 for name in ("observations", "sleep_intervals", "manual_entries", "manual_override_backups")):
        raise BackupTooLarge("数据条数超过 JSON 备份上限（每类 300 万条），当前版本无法安全导出或恢复这么大的备份。")
    validate_backup(payload)
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_BACKUP_BYTES:
        raise BackupTooLarge("数据超过 JSON 备份上限（112 MiB），当前版本无法安全导出或恢复这么大的备份。")
    return data


def _next_month(day):
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


def csv_daily(snapshot, now):
    """UTF-8 daily summary using exactly the dashboard's published records.

    Include unknown dates within months with data, but do not invent future days.
    Raw pending observations are included only in the full JSON backup.
    """
    settings = snapshot["settings"]
    zone = ZoneInfo(settings["timezone"])
    today = datetime.fromtimestamp(now, zone).date()
    watermark = snapshot["metadata"].get("published_seq", 0)
    samples = sorted((s for s in snapshot["observations"] if s["id"] <= watermark and s["ts"] <= now),
                     key=lambda s: (s["ts"], s["id"]))
    manual = [entry for entry in snapshot["manual_entries"] if date.fromisoformat(entry["date"]) <= today]
    sleeps = [s for s in snapshot["sleep_intervals"] if not s["abandoned"] and s["start"] <= now]
    months = {datetime.fromtimestamp(s["ts"], zone).date().replace(day=1) for s in samples}
    months.update(date.fromisoformat(e["date"]).replace(day=1) for e in manual)
    for s in sleeps:
        month = datetime.fromtimestamp(s["start"], zone).date().replace(day=1)
        last = datetime.fromtimestamp(min(s["end"] if s["end"] is not None else now, now), zone).date().replace(day=1)
        while month <= last:
            months.add(month)
            month = _next_month(month)

    timestamps = [s["ts"] for s in samples]
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["date", "timezone", "status", "work_hours", "vpn_hours", "sleep_estimated_hours",
                     "manual_kind", "income", "currency", "actual_hourly_rate", "rate_status"])
    for month in sorted(months):
        next_month = _next_month(month)
        start = datetime(month.year, month.month, 1, tzinfo=zone).timestamp()
        end = datetime(next_month.year, next_month.month, 1, tzinfo=zone).timestamp()
        # Include adjacent boundary samples so a connection spanning midnight
        # has the same accounting as the dashboard.
        monthly_samples = samples[bisect_left(timestamps, start - 45):bisect_right(timestamps, end + 45)]
        monthly_manual = [e for e in manual if e["date"][:7] == month.isoformat()[:7]]
        monthly_sleeps = [s for s in sleeps if s["start"] < end and (s["end"] is None or s["end"] >= start)]
        for day in calendar_month(monthly_samples, settings, month, now, monthly_manual, monthly_sleeps):
            if date.fromisoformat(day["date"]) > today:
                break
            writer.writerow([day["date"], settings["timezone"], day["status"], day["work_hours"],
                             day["vpn_work_hours"], day["sleep_estimated_hours"], day["manual_kind"] or "",
                             "" if day["income"] is None else day["income"], settings["currency"],
                             "" if day["actual_rate"] is None else day["actual_rate"], day["rate_status"]])
    # BOM makes UTF-8 CSV open reliably in spreadsheet applications.
    return out.getvalue().encode("utf-8-sig")


def validate_backup(payload, directory=None):
    """Validate the whole backup before any local data is touched.

    VPN verification is deliberately not restored on a different machine;
    callers pause collection until the user chooses to enable it again.
    """
    from store import _manual_date, _manual_minute, validate_settings

    def fail():
        raise ValueError("备份格式无效或包含不受支持的数据")

    def timestamp(value, optional=False):
        if optional and value is None:
            return
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            fail()
        try:
            datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OverflowError, OSError):
            fail()

    required = {"format", "version", "exported_at", "settings", "observations", "sleep_intervals",
                "manual_entries", "manual_override_backups", "metadata"}
    if not isinstance(payload, dict) or set(payload) != required or payload["format"] != "hourly-rate-backup" or type(payload["version"]) is not int or payload["version"] != 1:
        fail()
    try:
        exported = datetime.fromisoformat(payload["exported_at"])
        if exported.tzinfo is None:
            fail()
    except (TypeError, ValueError):
        fail()
    settings = validate_settings(payload["settings"], directory=directory)
    settings["tracking_enabled"] = False
    zone = ZoneInfo(settings["timezone"])
    for name in ("observations", "sleep_intervals", "manual_entries", "manual_override_backups"):
        if not isinstance(payload[name], list) or len(payload[name]) > 3_000_000:
            fail()
    previous_id = 0
    for item in payload["observations"]:
        if not isinstance(item, dict) or set(item) != {"id", "ts", "state"} or type(item["id"]) is not int or not previous_id < item["id"] < 2**62 or item["state"] not in ("connected", "disconnected", "unknown"):
            fail()
        timestamp(item["ts"])
        previous_id = item["id"]

    previous_end, open_sleep, sleep_starts = None, False, set()
    for item in payload["sleep_intervals"]:
        if not isinstance(item, dict) or set(item) != {"start", "end", "state", "last_sample_ts", "abandoned"} or type(item["abandoned"]) is not bool or item["state"] not in ("connected", "disconnected", "unknown"):
            fail()
        timestamp(item["start"]); timestamp(item["end"], True); timestamp(item["last_sample_ts"], True)
        if item["start"] in sleep_starts or (item["end"] is not None and item["end"] < item["start"]):
            fail()
        sleep_starts.add(item["start"])
        if not item["abandoned"]:
            if open_sleep or (previous_end is not None and item["start"] < previous_end):
                fail()
            open_sleep = item["end"] is None
            previous_end = item["end"]

    def valid_intervals(intervals, empty=False):
        if not isinstance(intervals, list) or not (0 if empty else 1) <= len(intervals) <= 12:
            fail()
        for span in intervals:
            if not isinstance(span, dict) or set(span) != {"start", "end"}:
                fail()
            if _manual_minute(span["end"], end=True) <= _manual_minute(span["start"]):
                fail()

    def valid_entries(entries, backup=False):
        found = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("kind") not in ("daily_total", "intervals", "intervals_override"):
                fail()
            kind = entry["kind"]
            required_entry = {"date", "kind", "note", "hours" if kind == "daily_total" else "intervals"}
            extra = {"edit_cutoff", "edit_cutoff_local", "tail_intervals", "present_closed"} if kind == "intervals_override" else set()
            if not required_entry <= set(entry) or set(entry) - required_entry - extra:
                fail()
            day = _manual_date(entry["date"])
            if day == date.max or entry["date"] in found or not isinstance(entry["note"], str) or len(entry["note"]) > 500 or (backup and kind == "intervals_override"):
                fail()
            if kind == "daily_total":
                hours = entry["hours"]
                if type(hours) not in (int, float) or not math.isfinite(hours) or not 0 <= hours <= 24:
                    fail()
            else:
                valid_intervals(entry["intervals"], empty=kind == "intervals_override")
                if "present_closed" in entry and type(entry["present_closed"]) is not bool:
                    fail()
                if "edit_cutoff" in entry:
                    timestamp(entry["edit_cutoff"])
                    if type(entry["edit_cutoff"]) is not int or entry["edit_cutoff"] % 60:
                        fail()
                if "edit_cutoff_local" in entry:
                    if "edit_cutoff" not in entry:
                        fail()
                    _manual_minute(entry["edit_cutoff_local"])
                if "edit_cutoff" in entry:
                    # Match _manual_records: a stored local wall time follows
                    # the user's selected timezone when that setting changes.
                    start = datetime(day.year, day.month, day.day, tzinfo=zone).timestamp()
                    next_day = day + timedelta(days=1)
                    end = datetime(next_day.year, next_day.month, next_day.day, tzinfo=zone).timestamp()
                    if "edit_cutoff_local" in entry:
                        minute = _manual_minute(entry["edit_cutoff_local"])
                        cutoff = datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=zone).timestamp()
                    else:
                        cutoff = entry["edit_cutoff"]
                    if not start <= cutoff <= end:
                        fail()
                if "tail_intervals" in entry:
                    if "edit_cutoff" not in entry:
                        fail()
                    valid_intervals(entry["tail_intervals"])
            found[entry["date"]] = entry
        return found

    entries = valid_entries(payload["manual_entries"])
    backups = valid_entries(payload["manual_override_backups"], backup=True)
    if any(day not in entries or entries[day]["kind"] != "intervals_override" for day in backups):
        fail()
    meta = payload["metadata"]
    if not isinstance(meta, dict) or any(key not in ("published_seq", "last_synced_at") and not key.startswith("verification:") for key in meta):
        fail()
    published = meta.get("published_seq", 0)
    if type(published) is not int or not 0 <= published <= previous_id:
        fail()
    timestamp(meta.get("last_synced_at"), True)
    return {"settings": settings, "observations": payload["observations"],
            "sleep_intervals": payload["sleep_intervals"], "manual_entries": payload["manual_entries"],
            "manual_override_backups": payload["manual_override_backups"],
            "metadata": {"published_seq": published, "last_synced_at": meta.get("last_synced_at")}}
