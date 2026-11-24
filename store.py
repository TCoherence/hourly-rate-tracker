"""A local observation queue with an atomic publication watermark."""
from __future__ import annotations

from datetime import date, datetime, time as datetime_time, timedelta
import json
import hashlib
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core import validate_salary_amount, validate_salary_history, validate_theoretical_daily_hours
from vpn import UUID, LOCAL_STATUS_SCRIPT, validate_status_script
from timezone_detect import detect_system_timezone
from legacy_compat import migrate_settings

DEFAULTS = {"annual_salary": None, "salary_history": [], "currency": "USD", "timezone": "America/Los_Angeles",
            "theoretical_daily_hours": 8,
            "work_start": "09:00", "work_end": "17:00", "workdays": [0, 1, 2, 3, 4],
            "provider": "disabled", "service_id": "", "status_script_path": "", "tracking_enabled": False,
            "pause_on_sleep": True, "night_pause_enabled": False,
            "night_pause_start": "00:00", "night_pause_end": "09:00", "manual_pauses": [],
            "screen_alert_enabled": True, "screen_alert_hours": 4, "screen_alerts": []}


def resolve_local_adapter(settings, directory):
    """Move only the former project-local default; preserve user-chosen scripts.

    This affects the effective setting, not the stored database row.  A backup
    can therefore be read at any data directory without rewriting its history.
    """
    result = dict(settings)
    if result["provider"] == "script" and result["status_script_path"] == LOCAL_STATUS_SCRIPT:
        result["status_script_path"] = str(Path(directory).expanduser().resolve() / "adapters" / "status")
    return result


def validate_settings(patch, old=None, directory=None):
    if not isinstance(patch, dict) or set(patch) - set(DEFAULTS):
        raise ValueError("设置中包含不支持的字段")
    s = dict(DEFAULTS)
    s.update(old or {})
    s.update(patch)
    # Upgrade old settings in memory; the database is not rewritten on read.
    s = migrate_settings(s, directory, LOCAL_STATUS_SCRIPT)
    validate_salary_amount(s["annual_salary"], optional=True)
    s["salary_history"] = validate_salary_history(s["salary_history"])
    s["theoretical_daily_hours"] = validate_theoretical_daily_hours(s["theoretical_daily_hours"])
    if s["currency"] not in ("USD", "CNY", "EUR", "GBP", "CAD", "JPY"):
        raise ValueError("不支持的币种")
    if not isinstance(s["timezone"], str) or len(s["timezone"]) > 80:
        raise ValueError("无效时区")
    try:
        ZoneInfo(s["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("请输入有效时区，例如 America/Los_Angeles") from None
    for key in ("work_start", "work_end", "night_pause_start", "night_pause_end"):
        value = s[key]
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError("工作时间格式应为 HH:MM")
        try:
            h, m = map(int, value.split(":"))
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError()
        except ValueError:
            raise ValueError("无效工作时间") from None
    if s["work_end"] <= s["work_start"]:
        raise ValueError("第一版支持同一天内的排班，结束时间须晚于开始时间")
    wd = s["workdays"]
    if not isinstance(wd, list) or not wd or len(wd) > 7 or any(type(x) is not int or x not in range(7) for x in wd):
        raise ValueError("请至少选择一个工作日")
    s["workdays"] = sorted(set(wd))
    if s["provider"] not in ("disabled", "system", "verified_system", "script", "cisco"):
        raise ValueError("尚不支持这款 VPN；请选择已适配的类型")
    script_path = s["status_script_path"]
    if not isinstance(script_path, str) or len(script_path) > 4096:
        raise ValueError("无效的状态脚本路径")
    if script_path:
        validate_status_script(script_path)
    if not isinstance(s["service_id"], str) or len(s["service_id"]) > 36:
        raise ValueError("无效的系统 VPN 标识")
    if s["service_id"] and not UUID.fullmatch(s["service_id"]):
        raise ValueError("系统 VPN 标识应为 UUID")
    if type(s["tracking_enabled"]) is not bool:
        raise ValueError("无效的采集开关")
    if type(s["pause_on_sleep"]) is not bool:
        raise ValueError("无效的睡眠计时开关")
    if type(s["night_pause_enabled"]) is not bool:
        raise ValueError("无效的夜间暂停开关")
    if type(s["screen_alert_enabled"]) is not bool:
        raise ValueError("无效的熄屏提醒开关")
    if type(s["screen_alert_hours"]) not in (int, float) or not math.isfinite(s["screen_alert_hours"]) or not 1 <= s["screen_alert_hours"] <= 24:
        raise ValueError("熄屏提醒时间须为 1 至 24 小时")
    alerts = s["screen_alerts"]
    if not isinstance(alerts, list) or len(alerts) > 1000:
        raise ValueError("无效的熄屏提醒记录")
    seen = set()
    for alert in alerts:
        if not isinstance(alert, dict) or set(alert) != {"id", "start", "end", "status"}:
            raise ValueError("无效的熄屏提醒记录")
        ident, begin, end = alert["id"], alert["start"], alert["end"]
        if not isinstance(ident, str) or not 1 <= len(ident) <= 64 or ident in seen or alert["status"] not in ("pending", "kept"):
            raise ValueError("无效的熄屏提醒记录")
        seen.add(ident)
        if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in (begin, end)) or end < begin:
            raise ValueError("无效的熄屏提醒时间")
        try:
            datetime.fromtimestamp(begin, ZoneInfo("UTC")); datetime.fromtimestamp(end, ZoneInfo("UTC"))
        except (ValueError, OverflowError, OSError):
            raise ValueError("无效的熄屏提醒时间") from None
    pauses = s["manual_pauses"]
    if not isinstance(pauses, list) or len(pauses) > 50000:
        raise ValueError("无效的手动暂停记录")
    previous_end = 0
    for index, interval in enumerate(pauses):
        if not isinstance(interval, dict) or set(interval) != {"start", "end"}:
            raise ValueError("无效的手动暂停记录")
        start, end = interval["start"], interval["end"]
        if type(start) not in (int, float) or not math.isfinite(start) or start < previous_end:
            raise ValueError("无效的手动暂停开始时间")
        if end is None:
            if index != len(pauses) - 1:
                raise ValueError("无效的手动暂停结束时间")
        elif type(end) not in (int, float) or not math.isfinite(end) or end < start:
            raise ValueError("无效的手动暂停结束时间")
        for stamp in (start, end):
            if stamp is not None:
                try:
                    datetime.fromtimestamp(stamp, ZoneInfo("UTC"))
                except (ValueError, OverflowError, OSError):
                    raise ValueError("无效的手动暂停时间") from None
        previous_end = end if end is not None else start
    if s["night_pause_start"] == s["night_pause_end"]:
        raise ValueError("夜间暂停的开始和结束时间不能相同")
    if s["tracking_enabled"] and (s["provider"] == "disabled" or (s["provider"] in ("system", "verified_system") and not s["service_id"]) or (s["provider"] == "script" and not script_path)):
        raise ValueError("开启采集前请先配置公司 VPN")
    return s


def _manual_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("补记日期须为 YYYY-MM-DD")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise ValueError("补记日期无效，请使用 YYYY-MM-DD") from None
    if day.isoformat() != value:
        raise ValueError("补记日期须为 YYYY-MM-DD")
    return day


def _manual_minute(value, *, end=False):
    if end and value == "24:00":
        return 1440
    if (not isinstance(value, str) or len(value) != 5 or value[2] != ":"
            or any(char not in "0123456789" for char in value[:2] + value[3:])):
        raise ValueError("补记时间须为 HH:MM，结束时间可使用 24:00")
    hour, minute = int(value[:2]), int(value[3:])
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError("补记时间无效，请检查小时和分钟")
    return hour * 60 + minute


def _validate_manual_entries(entries, timezone, now=None):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 366:
        raise ValueError("每次请提交 1 至 366 天的补记")
    now = time.time() if now is None else now
    zone = ZoneInfo(timezone)
    today = datetime.fromtimestamp(now, zone).date()
    dates = set()
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("补记须包含日期和记录类型")
        kind = entry.get("kind")
        if kind not in ("daily_total", "intervals", "intervals_override"):
            raise ValueError("补记类型须为每日总时长或具体时间段")
        required = {"date", "kind", "hours" if kind == "daily_total" else "intervals"}
        allowed = required | {"note"} | ({"edit_cutoff", "edit_revision", "present_end", "present_closed"} if kind == "intervals_override" else set())
        if not required.issubset(entry) or set(entry) - allowed:
            raise ValueError("补记字段不完整或包含不支持的字段")
        day = _manual_date(entry["date"])
        if day > today:
            raise ValueError("不能补记未来日期，请检查本机设置中的时区")
        if day in dates:
            raise ValueError("同一次补记中，每个日期只能出现一次")
        dates.add(day)
        note = entry.get("note", "")
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError("补记备注须为文字，且不超过 500 字")
        value = {"date": day.isoformat(), "kind": kind, "note": note}
        if kind == "daily_total":
            if day == today:
                raise ValueError("今天仍在计时，请使用具体时间段补记；每日总时长仅用于过去日期")
            hours = entry["hours"]
            if type(hours) not in (int, float) or not 0 <= hours <= 24 or not math.isfinite(hours):
                raise ValueError("每日补记时长须为 0 至 24 小时的有限数字")
            value["hours"] = float(hours)
        else:
            cutoff = entry.get("edit_cutoff")
            if kind == "intervals_override" and day == today:
                day_start = datetime.combine(day, datetime.min.time(), zone)
                next_start = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone)
                if day_start.utcoffset() != next_start.utcoffset():
                    raise ValueError("今天发生时区偏移变化，无法安全修正，请改用补充时段")
                if (type(cutoff) is not int or cutoff < 0 or cutoff % 60 or cutoff > now
                        or datetime.fromtimestamp(cutoff, zone).date() != day):
                    raise ValueError("请重新读取今天的记录，取得有效的修正截止时间")
                revision = entry.get("edit_revision")
                if not isinstance(revision, str) or len(revision) != 64:
                    raise ValueError("请重新读取今天的记录，取得修正版本")
                value["edit_cutoff"] = cutoff
                value["edit_cutoff_local"] = datetime.fromtimestamp(cutoff, zone).strftime("%H:%M")
                value["edit_revision"] = revision
            elif cutoff is not None or entry.get("edit_revision") is not None:
                raise ValueError("过去日期的整日修正不能指定截止时间")
            present_end = entry.get("present_end")
            present_closed = entry.get("present_closed", False)
            if type(present_closed) is not bool:
                raise ValueError("至今记录状态无效")
            if present_closed:
                if day != today:
                    raise ValueError("至今记录状态与当前修正不符")
                value["present_closed"] = True
            if present_end is not None:
                if kind != "intervals_override" or day != today:
                    raise ValueError("至今只能用于今天的修正")
                present_minute = _manual_minute(present_end)
                present_at = datetime.combine(day, datetime_time(present_minute // 60, present_minute % 60), zone).timestamp()
                if present_at > now or present_at <= cutoff:
                    raise ValueError("至今时间无效，请刷新当前记录后重试")
                # A manual "present" is a one-shot interval ending at save;
                # reopening must not silently keep extending that interval.
                value["present_closed"] = True
            intervals = entry["intervals"]
            if not isinstance(intervals, list) or not (0 if kind == "intervals_override" else 1) <= len(intervals) <= 12:
                raise ValueError("每天请填写 1 至 12 个补记时间段")
            ranges = []
            present_tail = None
            for index, interval in enumerate(intervals):
                if not isinstance(interval, dict) or set(interval) != {"start", "end"}:
                    raise ValueError("每个补记时间段须包含开始和结束时间")
                start = _manual_minute(interval["start"])
                end = _manual_minute(interval["end"], end=True)
                if end <= start:
                    raise ValueError("补记时间段须在同一天内，且结束时间晚于开始时间")
                if kind == "intervals_override" and day == today:
                    end_at = (datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).timestamp()
                              if end == 1440 else datetime.combine(day, datetime_time(end // 60, end % 60), zone).timestamp())
                    if end_at > cutoff:
                        if (present_end is None or index != len(intervals) - 1
                                or interval["end"] != present_end):
                            raise ValueError("今天的修正时段不能超过加载时的截止时间")
                        cutoff_local = datetime.fromtimestamp(cutoff, zone)
                        cutoff_minute = cutoff_local.hour * 60 + cutoff_local.minute
                        tail_start = max(start, cutoff_minute)
                        present_tail = (tail_start, end)
                        end = min(end, cutoff_minute)
                if start < end:
                    ranges.append((start, end))
            if present_end is not None and present_tail is None:
                raise ValueError("至今必须是最后一段且晚于修正截止时间")
            merged = []
            for start, end in sorted(ranges):
                # Adjacent ranges may represent an intentional split. Keep
                # their shared boundary while still deduplicating overlap.
                if merged and start < merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            value["intervals"] = [{"start": f"{start // 60:02d}:{start % 60:02d}",
                                    "end": f"{end // 60:02d}:{end % 60:02d}"}
                                   for start, end in merged]
            if present_tail is not None:
                value["_present_tail"] = {"start": f"{present_tail[0] // 60:02d}:{present_tail[0] % 60:02d}",
                                          "end": f"{present_tail[1] // 60:02d}:{present_tail[1] % 60:02d}"}
        result.append(value)
    return result


class Store:
    def __init__(self, directory):
        self.path = Path(directory).expanduser().resolve()
        existed = self.path.exists()
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not existed:
            self.path.chmod(0o700)
        self.lock = threading.RLock()
        self.db_path = self.path / "records.sqlite3"
        new_database = not self.db_path.exists()
        self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.db_path.chmod(0o600)
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS observations(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, state TEXT NOT NULL
                CHECK(state IN ('connected','disconnected','unknown')));
            CREATE INDEX IF NOT EXISTS observations_time ON observations(ts);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manual_entries(date TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manual_override_backups(date TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sleep_intervals(
                start REAL PRIMARY KEY, end REAL,
                state TEXT NOT NULL CHECK(state IN ('connected','disconnected','unknown')),
                last_sample_ts REAL, abandoned INTEGER NOT NULL DEFAULT 0,
                CHECK(end IS NULL OR end >= start));
        """)
        if new_database:
            # Freeze the detected timezone for the lifetime of a new database.
            # Existing databases (including those without a saved settings row)
            # retain their previous defaults and are never silently reinterpreted.
            self._set("settings", {**DEFAULTS, "timezone": detect_system_timezone()})
        self.db.commit()

    def _get(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, key, value):
        self.db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, ensure_ascii=False, allow_nan=False)))

    def settings(self):
        with self.lock:
            return resolve_local_adapter(validate_settings(self._get("settings", DEFAULTS), directory=self.path), self.path)

    def save_settings(self, patch):
        with self.lock:
            value = resolve_local_adapter(validate_settings(patch, self.settings(), directory=self.path), self.path)
            self._set("settings", value)
            self.db.commit()
            return value

    def manual_entries(self):
        with self.lock:
            rows = self.db.execute("SELECT payload FROM manual_entries ORDER BY date").fetchall()
            return [json.loads(payload) for (payload,) in rows]

    def manual_revision(self, day):
        with self.lock:
            row = self.db.execute("SELECT payload FROM manual_entries WHERE date=?", (day,)).fetchone()
            return hashlib.sha256((row[0] if row else "").encode()).hexdigest()

    def save_manual_entries(self, entries, now=None, precommit=None):
        with self.lock:
            validated = _validate_manual_entries(entries, self.settings()["timezone"], now)
            with self.db:
                for entry in validated:
                    old = self.db.execute("SELECT payload FROM manual_entries WHERE date=?", (entry["date"],)).fetchone()
                    previous = json.loads(old[0]) if old else None
                    revision = entry.pop("edit_revision", None)
                    if revision is not None and revision != hashlib.sha256((old[0] if old else "").encode()).hexdigest():
                        raise ValueError("当天记录已发生变化，请重新读取后再修正")
                    present_tail = entry.pop("_present_tail", None)
                    if entry["kind"] == "intervals_override":
                        if old and previous["kind"] != "intervals_override":
                            self.db.execute("INSERT OR REPLACE INTO manual_override_backups VALUES (?,?)", (entry["date"], old[0]))
                        if "edit_cutoff" in entry and previous:
                            tail = (previous.get("tail_intervals", []) if previous["kind"] == "intervals_override"
                                    else previous.get("intervals", []) if previous["kind"] == "intervals" else [])
                            if present_tail:
                                tail = list(tail) + [present_tail]
                            if tail:
                                spans = sorted((_manual_minute(item["start"]), _manual_minute(item["end"], end=True)) for item in tail)
                                merged = []
                                for start, end in spans:
                                    if merged and start < merged[-1][1]:
                                        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                                    else:
                                        merged.append((start, end))
                                if len(merged) > 12:
                                    raise ValueError("保留的手动时段超过 12 段，请先整理后再保存")
                                entry["tail_intervals"] = [{"start": f"{start // 60:02d}:{start % 60:02d}",
                                                            "end": f"{end // 60:02d}:{end % 60:02d}"} for start, end in merged]
                        elif present_tail:
                            entry["tail_intervals"] = [present_tail]
                    else:
                        self.db.execute("DELETE FROM manual_override_backups WHERE date=?", (entry["date"],))
                rows = [(entry["date"], json.dumps(entry, ensure_ascii=False, allow_nan=False,
                                                  sort_keys=True, separators=(",", ":")))
                        for entry in validated]
                self.db.executemany("""
                    INSERT INTO manual_entries(date,payload) VALUES(?,?)
                    ON CONFLICT(date) DO UPDATE SET payload=excluded.payload
                    WHERE manual_entries.payload != excluded.payload
                """, rows)
                if precommit is not None:
                    # Run under the SQLite transaction so a concurrent state
                    # change rolls back the manual entry and any backup row.
                    precommit()
            return self.manual_entries()

    def delete_manual_entry(self, day):
        day = _manual_date(day).isoformat()
        with self.lock:
            with self.db:
                backup = self.db.execute("SELECT payload FROM manual_override_backups WHERE date=?", (day,)).fetchone()
                if backup:
                    self.db.execute("UPDATE manual_entries SET payload=? WHERE date=?", (backup[0], day))
                    self.db.execute("DELETE FROM manual_override_backups WHERE date=?", (day,))
                else:
                    self.db.execute("DELETE FROM manual_entries WHERE date=?", (day,))
            return self.manual_entries()

    def record(self, ts, state):
        if state not in ("connected", "disconnected", "unknown") or not math.isfinite(ts):
            raise ValueError("Invalid observation")
        with self.lock:
            self.db.execute("INSERT INTO observations(ts,state) VALUES(?,?)", (ts, state))
            self.db.commit()

    def begin_sleep(self, ts, state, last_sample_ts):
        """Persist a real system-sleep event, ignoring duplicate notifications."""
        if (type(ts) not in (int, float) or not math.isfinite(ts)
                or state not in ("connected", "disconnected", "unknown")
                or (last_sample_ts is not None and (type(last_sample_ts) not in (int, float)
                    or not math.isfinite(last_sample_ts)))):
            raise ValueError("无效的睡眠事件")
        with self.lock, self.db:
            if self.db.execute("SELECT 1 FROM sleep_intervals WHERE end IS NULL AND abandoned=0").fetchone():
                return False
            last = self.db.execute("SELECT MAX(end) FROM sleep_intervals").fetchone()[0]
            if last is not None and ts < last:
                return False
            cursor = self.db.execute("INSERT OR IGNORE INTO sleep_intervals(start,state,last_sample_ts) VALUES(?,?,?)",
                                     (ts, state, last_sample_ts))
            return cursor.rowcount > 0

    def end_sleep(self, ts):
        """Only pair a wake event with this process's still-open sleep event."""
        if type(ts) not in (int, float) or not math.isfinite(ts):
            raise ValueError("无效的唤醒事件")
        with self.lock, self.db:
            # Wall-clock rollback makes the interval unusable, not negative work.
            self.db.execute("UPDATE sleep_intervals SET abandoned=1 WHERE end IS NULL AND start>?", (ts,))
            cursor = self.db.execute("UPDATE sleep_intervals SET end=? WHERE end IS NULL AND abandoned=0", (ts,))
            return cursor.rowcount > 0

    def abandon_open_sleep(self):
        """Call at process start; downtime cannot complete an old sleep event."""
        with self.lock, self.db:
            self.db.execute("UPDATE sleep_intervals SET abandoned=1 WHERE end IS NULL AND abandoned=0")

    def sleep_intervals(self, since=None):
        with self.lock:
            rows = self.db.execute("""SELECT start,end,state,last_sample_ts FROM sleep_intervals
                WHERE abandoned=0 AND (end IS NULL OR end>=?) ORDER BY start""", (since or 0,)).fetchall()
            return [{"start": start, "end": end, "state": state, "last_sample_ts": checked}
                    for start, end, state, checked in rows]

    def sync(self, now=None):
        with self.lock:
            seq = self.db.execute("SELECT COALESCE(MAX(id),0) FROM observations").fetchone()[0]
            self._set("published_seq", seq)
            self._set("last_synced_at", time.time() if now is None else now)
            self.db.commit()
            return seq

    def published_samples(self, since=None, until=None):
        with self.lock:
            seq = self._get("published_seq", 0)
            rows = self.db.execute("SELECT ts,state FROM observations WHERE id<=? AND ts>=? AND ts<=? ORDER BY ts,id",
                                   (seq, since or 0, until if until is not None else float('inf'))).fetchall()
            return [{"ts": t, "state": state} for t, state in rows]

    def recent_samples(self, since, until):
        """Read actual observations, including those not yet published."""
        with self.lock:
            rows = self.db.execute("SELECT ts,state FROM observations WHERE ts>=? AND ts<=? ORDER BY ts DESC,id DESC",
                                   (since, until)).fetchall()
            return [{"ts": t, "state": state} for t, state in rows]

    def sync_status(self):
        with self.lock:
            seq = self._get("published_seq", 0)
            count = self.db.execute("SELECT COUNT(*) FROM observations WHERE id>?", (seq,)).fetchone()[0]
            return {"pending_count": count, "last_synced_at": self._get("last_synced_at"), "published_seq": seq}

    def export_snapshot(self):
        """Take one consistent, read-only snapshot, including pending samples.

        Session credentials are generated in memory and never enter this export.
        """
        with self.lock:
            settings = self.settings()
            observations = [{"id": i, "ts": ts, "state": state} for i, ts, state in
                            self.db.execute("SELECT id,ts,state FROM observations ORDER BY id")]
            sleeps = [{"start": start, "end": end, "state": state, "last_sample_ts": sample,
                       "abandoned": bool(abandoned)} for start, end, state, sample, abandoned in
                      self.db.execute("SELECT start,end,state,last_sample_ts,abandoned FROM sleep_intervals ORDER BY start")]
            manual = [json.loads(payload) for (payload,) in
                      self.db.execute("SELECT payload FROM manual_entries ORDER BY date")]
            backups = [json.loads(payload) for (payload,) in
                       self.db.execute("SELECT payload FROM manual_override_backups ORDER BY date")]
            meta = {key: json.loads(value) for key, value in
                    self.db.execute("SELECT key,value FROM meta WHERE key != 'settings' ORDER BY key")}
            return {"settings": settings, "observations": observations, "sleep_intervals": sleeps,
                    "manual_entries": manual, "manual_override_backups": backups, "metadata": meta}

    def restore_snapshot(self, snapshot):
        """Replace validated data atomically; open sleep events cannot cross restarts."""
        with self.lock, self.db:
            self.db.execute("DELETE FROM observations")
            # An old or untrusted sequence must not survive a restore; inserting
            # the validated IDs below rebuilds it from the restored data.
            self.db.execute("DELETE FROM sqlite_sequence WHERE name='observations'")
            self.db.execute("DELETE FROM sleep_intervals")
            self.db.execute("DELETE FROM manual_entries")
            self.db.execute("DELETE FROM manual_override_backups")
            self.db.execute("DELETE FROM meta")
            self.db.executemany("INSERT INTO observations(id,ts,state) VALUES(?,?,?)",
                                [(s["id"], s["ts"], s["state"]) for s in snapshot["observations"]])
            self.db.executemany("INSERT INTO sleep_intervals(start,end,state,last_sample_ts,abandoned) VALUES(?,?,?,?,?)",
                                [(s["start"], s["end"], s["state"], s["last_sample_ts"],
                                  int(s["abandoned"] or s["end"] is None)) for s in snapshot["sleep_intervals"]])
            for table, key in (("manual_entries", "manual_entries"), ("manual_override_backups", "manual_override_backups")):
                self.db.executemany("INSERT INTO " + table + "(date,payload) VALUES(?,?)",
                    [(e["date"], json.dumps(e, ensure_ascii=False, allow_nan=False, sort_keys=True,
                                            separators=(",", ":"))) for e in snapshot[key]])
            self._set("settings", snapshot["settings"])
            self._set("published_seq", snapshot["metadata"]["published_seq"])
            self._set("last_synced_at", snapshot["metadata"]["last_synced_at"])

    def close(self):
        with self.lock:
            self.db.close()

    def verification(self, service_id):
        with self.lock:
            states = self._get("verification:" + service_id, []) if service_id else []
            return {"service_id": service_id, "verified_states": states,
                    "verified": set(states) == {"connected", "disconnected"}}

    def verify_state(self, service_id, state):
        if not UUID.fullmatch(service_id) or state not in ("connected", "disconnected"):
            raise ValueError("无效核对状态")
        with self.lock:
            states = set(self.verification(service_id)["verified_states"])
            states.add(state)
            self._set("verification:" + service_id, sorted(states))
            self.db.commit()
            return self.verification(service_id)

    def invalidate_verification(self, service_id, now=None):
        """Revoke trust and pause the affected collector in one transaction."""
        if not UUID.fullmatch(service_id):
            raise ValueError("无效核对服务")
        with self.lock, self.db:
            settings = self.settings()
            paused = (settings["provider"] == "verified_system"
                      and settings["service_id"] == service_id
                      and settings["tracking_enabled"])
            self._set("verification:" + service_id, [])
            if paused:
                settings["tracking_enabled"] = False
                self._set("settings", settings)
                self.db.execute("INSERT INTO observations(ts,state) VALUES(?,?)",
                                (time.time() if now is None else now, "unknown"))
        return {**self.verification(service_id), "tracking_paused": paused}
