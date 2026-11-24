#!/usr/bin/env python3
"""Hourly Rate MVP: a loopback-only dashboard and read-only Mac VPN collector.

No external upload destination, outbound HTTP client, analytics, CDN, or cloud SDK.
"""
from __future__ import annotations

import argparse
import errno
from datetime import date, datetime, timedelta
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import sqlite3
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from core import summarize, calendar_month, history_day, night_pause_state, MAX_SAMPLE_GAP
from exporting import (BackupTooLarge, MAX_RESTORE_BYTES, serialize_backup,
                       csv_daily, validate_backup)
from binary_backup import MAX_SQLITE_BYTES, snapshot_file, restore_sqlite_file
from autostart import AutostartError, LoginItem
from instance import AlreadyRunning, InstanceLock
from store import Store
from power import PowerMonitor
from screen_monitor import DisplayMonitor
from screen_alerts import ScreenAlertTracker
from browser_auth import BrowserGrants, write_private_json
import vpn

ROOT = Path(__file__).resolve().parent
SYNC_SECONDS = 60
POLL_SECONDS = 15
DEFAULT_DATA = Path.home() / "Library" / "Application Support" / "HourlyRateMVP"
PERIODS = {"today", "week", "month", "quarter", "half", "year", "rolling_year"}
COLLECTOR_LOG = logging.getLogger("hourly_rate.collector")


def iso(ts):
    return datetime.fromtimestamp(ts, ZoneInfo("UTC")).isoformat() if ts is not None else None


def _parse_log_timestamp(value):
    """Accept historical compact offsets on Python 3.10 as well as ISO offsets."""
    # Python 3.10's fromisoformat accepts +00:00 but not the +0000 output
    # emitted by the logging formatter. Normalize before parsing either form.
    value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("备份含重复字段")
        value[key] = item
    return value


def _reject_json_constant(value):
    raise ValueError("备份含无效数字")


class Application:
    def __init__(self, directory, detector=vpn.detect, power_monitor_factory=PowerMonitor, display_monitor_factory=DisplayMonitor):
        self.store = Store(directory)
        self.detector = (lambda settings: vpn.detect(settings, compatibility_dir=self.store.path)) if detector is vpn.detect else detector
        self.token = secrets.token_urlsafe(32)
        self.session_token = secrets.token_urlsafe(32)
        self.pair_token = secrets.token_urlsafe(32)
        self.auth_lock = threading.RLock()
        self.browser_grants = BrowserGrants(self.store.path)
        self.stop_event = threading.Event()
        self.collector_wake = threading.Event()
        self.power_events = queue.SimpleQueue()
        self.system_sleeping = False
        self.power_error = None
        self.lock = threading.RLock()
        self.cache_lock = threading.Lock()
        self.cache = {}
        self.demo_samples = None
        self.demo_key = None
        self.state, self.message = "disabled", "采集尚未开启；可先查看演示"
        self.last_checked = None
        self.next_sync = time.time() + SYNC_SECONDS
        self.next_sync_mono = time.monotonic() + SYNC_SECONDS
        self.thread = None
        self._collector_provider = "disabled"
        self._logged_collector = None
        self.power_monitor = power_monitor_factory(self.on_power_event)
        self.display_monitor = display_monitor_factory()
        self.screen_tracker = ScreenAlertTracker(MAX_SAMPLE_GAP)
        self.screen_monitor_state = {"available": False, "message": "等待首次屏幕状态检查；未知时段不会触发提醒。"}

    def reset_screen_tracker(self):
        """Discard an unfinished interval after a restart or database restore."""
        self.screen_tracker = ScreenAlertTracker(MAX_SAMPLE_GAP)

    def _end_screen_candidate(self):
        if self.screen_tracker.alert_id is None:
            # No persisted reminder needs finalizing; do not re-read settings,
            # particularly when handling a failed settings read itself.
            self.screen_tracker.reset([])
            return
        settings = self.store.settings()
        alerts = [dict(item) for item in settings["screen_alerts"]]
        if self.screen_tracker.reset(alerts):
            self.store.save_settings({"screen_alerts": alerts})

    def _safely_end_screen_candidate(self):
        """Reminder failures must not interrupt sleep records or VPN tracking."""
        try:
            self._end_screen_candidate()
        except Exception:
            self.reset_screen_tracker()
            self.screen_monitor_state = {"available": False, "message": "屏幕提醒暂不可用，VPN 计时不受影响。"}

    def _observe_screen(self, settings):
        """Advance only across consecutive, independently confirmed samples."""
        if not settings["screen_alert_enabled"]:
            self.screen_monitor_state = {"available": False, "message": "熄屏提醒已关闭。"}
            self._safely_end_screen_candidate()
            return
        # System sleep boundaries are essential; never infer screen state when
        # that independent monitor has failed or a power event is pending.
        if self.power_monitor.status != "running" or self.power_monitor.error or self.power_error or self.system_sleeping or not self.power_events.empty():
            self.screen_monitor_state = {"available": False, "message": "睡眠状态暂不可用或正在变化；未知时段不会触发提醒。"}
            self._safely_end_screen_candidate()
            return
        asleep = self.display_monitor.read()
        if asleep is None:
            self.screen_monitor_state = {"available": False, "message": self.display_monitor.error or "屏幕状态未知，无法判断熄屏时段。"}
        else:
            self.screen_monitor_state = {"available": True, "message": "屏幕状态检测正常；仅在确认熄屏且自动计时时提醒。"}
        now = time.time()
        paused = bool(settings["manual_pauses"] and settings["manual_pauses"][-1]["end"] is None)
        night_paused, _ = night_pause_state(now, settings)
        eligible = (asleep is True and settings["tracking_enabled"] and self.state == "connected"
                    and not paused and not night_paused and self.power_events.empty())
        alerts = [dict(item) for item in settings["screen_alerts"]]
        if self.screen_tracker.observe(now, time.monotonic(), eligible, settings["screen_alert_hours"], alerts):
            self.store.save_settings({"screen_alerts": alerts})
        if self.screen_tracker.full:
            self.screen_monitor_state = {"available": False, "message": "待确认的熄屏提醒已达到上限，请先确认已有提醒；VPN 计时不受影响。"}

    def screen_alerts(self, settings):
        active = self.screen_tracker.alert_id
        return [{"id": a["id"], "start": iso(a["start"]), "end": iso(a["end"]),
                 "status": a["status"], "active": a["id"] == active}
                for a in settings["screen_alerts"] if a["status"] == "pending"]

    def keep_screen_alert(self, ident):
        if not isinstance(ident, str) or not ident or len(ident) > 64:
            raise ValueError("请选择有效的提醒")
        with self.lock:
            if self.screen_tracker.alert_id == ident:
                raise ValueError("这个时段仍在继续，请先暂停计时或等待它结束。")
            settings = self.store.settings()
            alerts = [dict(item) for item in settings["screen_alerts"]]
            alert = next((item for item in alerts if item["id"] == ident), None)
            if alert is None:
                raise ValueError("未找到这条提醒，请刷新后重试。")
            if alert["status"] != "kept":
                alert["status"] = "kept"
                self.store.save_settings({"screen_alerts": alerts})
            return {"ok": True}

    def on_power_event(self, event, timestamp):
        """Native notifications must never wait for SQLite or the VPN process."""
        if event in ("sleep", "wake") and not self.stop_event.is_set():
            self.power_events.put((event, timestamp, self.state, self.last_checked))
            self.collector_wake.set()

    def process_power_events(self):
        """Persist ordered notifications on the collector thread, then resample."""
        changed = False
        while True:
            try:
                event, timestamp, state, checked = self.power_events.get_nowait()
            except queue.Empty:
                break
            with self.lock:
                settings = self.store.settings()
                if event == "sleep":
                    self.system_sleeping = True
                    self._safely_end_screen_candidate()
                    if settings["tracking_enabled"]:
                        known_state = state if state in ("connected", "disconnected") else "unknown"
                        self.store.begin_sleep(timestamp, known_state, checked)
                else:
                    self.system_sleeping = False
                    self.store.end_sleep(timestamp)
                message = ("Mac 进入睡眠；睡眠工时按设置处理" if event == "sleep"
                           else "Mac 已唤醒；自动恢复检测 VPN")
                COLLECTOR_LOG.info(json.dumps({"event": "power_status", "provider": "system_power",
                                               "state": event, "message": message,
                                               "occurred_at": iso(timestamp)}, ensure_ascii=False))
                changed = True
        if changed:
            with self.cache_lock:
                self.cache.clear()
        return changed

    def recover_power_monitor(self):
        # A failed listener must not leave the independent VPN loop waiting for
        # a wake notification that can no longer arrive.
        if self.system_sleeping and (self.power_monitor.status != "running" or self.power_monitor.error):
            self.system_sleeping = False
            self.power_error = "系统睡眠识别中断；已恢复 VPN 检测，未确认的睡眠时段不做估算"
            with self.lock:
                self.store.abandon_open_sleep()
            return True
        return False

    def power_status(self):
        available = self.power_monitor.status == "running" and not (self.power_error or self.power_monitor.error)
        return {"available": available,
                "message": ("系统睡眠识别已开启，唤醒后自动恢复检测" if available else
                            self.power_error or self.power_monitor.error or "系统睡眠识别暂不可用；采样缺口仍按未知处理")}

    def log_collector(self):
        """Log first observation and changes, using only the adapter's safe status."""
        current = (self._collector_provider, self.state, self.message)
        if current != self._logged_collector:
            COLLECTOR_LOG.info(json.dumps({"event": "vpn_status", "provider": self._collector_provider,
                                           "state": self.state, "message": self.message}, ensure_ascii=False))
            self._logged_collector = current

    def sample(self):
        with self.lock:
            try:
                settings = self.store.settings()
            except Exception:
                # Do not retry a failed settings read in the failure/logging
                # path. A persisted alert retains its last confirmed endpoint.
                self.reset_screen_tracker()
                raise
            self._collector_provider = settings["provider"]
            self.state, self.message = self.detector(settings)
            self.last_checked = time.time() if settings["tracking_enabled"] else None
            if settings["tracking_enabled"]:
                self.store.record(self.last_checked, self.state if self.state in ("connected", "disconnected") else "unknown")
            try:
                self._observe_screen(settings)
            except Exception:
                # Screen monitoring is independent: never turn a successfully
                # sampled VPN state into unknown if a reminder fails.
                self.reset_screen_tracker()
                self.screen_monitor_state = {"available": False, "message": "屏幕提醒暂不可用，VPN 计时不受影响。"}
            self.log_collector()

    def sync(self):
        with self.lock:
            self.store.sync()
            self.next_sync = time.time() + SYNC_SECONDS
            self.next_sync_mono = time.monotonic() + SYNC_SECONDS
            with self.cache_lock:
                self.cache.clear()

    def check_script(self):
        """Read the CLI without changing collection, settings or observations."""
        try:
            settings = self.store.settings()
            state, message = self.detector({"provider": "script", "status_script_path": settings["status_script_path"],
                                            "tracking_enabled": True})
            return {"state": state, "message": message}
        except Exception:
            return {"state": "unknown", "message": "无法读取状态脚本；状态未知"}

    def status_log(self):
        """Expose only recent status events, never arbitrary service output."""
        lines = []
        for name in ("service.log", "autostart-service.log"):
            try:
                with (self.store.path / name).open("rb") as stream:
                    stream.seek(0, 2)
                    offset = max(0, stream.tell() - 128 * 1024)
                    stream.seek(offset)
                    if offset:
                        stream.readline()  # The tail may begin inside a line.
                    lines.extend(stream.read(128 * 1024).decode("utf-8", errors="replace").splitlines())
            except FileNotFoundError:
                continue
        entries = []
        for line in lines:
            timestamp, _, payload = line.partition(" ")
            try:
                parsed_time = _parse_log_timestamp(timestamp)
                event = json.loads(payload)
                if parsed_time.tzinfo is None or not isinstance(event, dict) or not isinstance(event.get("message"), str):
                    continue
                from legacy_compat import legacy_provider_for_log
                provider = legacy_provider_for_log(event.get("provider"), self.store.path)
                vpn_event = (event.get("event") == "vpn_status"
                             and provider is not None
                             and event.get("state") in ("disabled", "connected", "disconnected", "unknown"))
                power_event = (event.get("event") == "power_status" and event.get("provider") == "system_power"
                               and event.get("state") in ("sleep", "wake"))
                if not (vpn_event or power_event):
                    continue
                if power_event:
                    occurred = _parse_log_timestamp(event.get("occurred_at", ""))
                    if occurred.tzinfo is None:
                        continue
                    parsed_time = occurred
                entries.append((parsed_time.timestamp(), {"timestamp": parsed_time.isoformat(), "provider": event["provider"] if power_event else provider,
                                "state": event["state"], "message": event["message"][:2000]}))
            except (ValueError, TypeError, OverflowError, OSError):
                continue
        entries.sort(key=lambda item: item[0])
        return {"entries": [item[1] for item in entries[-30:]]}

    def settings(self, patch):
        with self.lock:
            if "manual_pauses" in patch or "screen_alerts" in patch:
                raise ValueError("请使用暂停按钮修改手动暂停状态")
            old = self.store.settings()
            # Validate before changing/closing anything.
            from store import resolve_local_adapter, validate_settings
            new = resolve_local_adapter(validate_settings(patch, old, directory=self.store.path), self.store.path)
            if new["tracking_enabled"] and new["provider"] == "verified_system" and not self.store.verification(new["service_id"])["verified"]:
                raise ValueError("系统 VPN 需要完成已连接和已断开两次状态核对")
            provider_changed = any(old[k] != new[k] for k in ("provider", "service_id", "status_script_path", "tracking_enabled"))
            if provider_changed:
                # A sleep spanning two collection configurations cannot safely
                # inherit either provider's last known state.
                self.store.abandon_open_sleep()
            if provider_changed and old["tracking_enabled"]:
                self.store.record(time.time(), "unknown")
            self.store.save_settings(new)
            if any(old[k] != new[k] for k in ("provider", "service_id", "status_script_path", "tracking_enabled", "night_pause_enabled", "night_pause_start", "night_pause_end", "timezone", "pause_on_sleep", "screen_alert_enabled", "screen_alert_hours")):
                self._safely_end_screen_candidate()
            if provider_changed:
                self.safe_sample()
            self.sync()
            return new

    def set_manual_pause(self, paused):
        """Persist precise manual pause boundaries without changing VPN samples."""
        if type(paused) is not bool:
            raise ValueError("请选择暂停或恢复计时")
        with self.lock:
            settings = self.store.settings()
            pauses = [dict(item) for item in settings["manual_pauses"]]
            active = bool(pauses and pauses[-1]["end"] is None)
            if paused == active:
                return {"paused": active}
            if paused:
                if not settings["tracking_enabled"]:
                    raise ValueError("请先在设置中启用 VPN 计时")
                # Confirm a boundary immediately, so the most recent work is
                # not lost merely because periodic samples lag behind the click.
                if not self.system_sleeping:
                    self.safe_sample()
                stamp = time.time()
                pauses.append({"start": stamp, "end": None})
            else:
                stamp = max(time.time(), pauses[-1]["start"])
                # Never infer a connected VPN across the manual resume boundary.
                if settings["tracking_enabled"]:
                    self.store.record(stamp, "unknown")
                pauses[-1]["end"] = stamp
            self.store.save_settings({"manual_pauses": pauses})
            if paused:
                self._safely_end_screen_candidate()
            if not paused and settings["tracking_enabled"] and not self.system_sleeping:
                self.safe_sample()
            self.sync()
            self.collector_wake.set()
            return {"paused": paused}

    def manual_entries(self):
        settings = self.store.settings()
        return {"entries": self.store.manual_entries(), "timezone": settings["timezone"],
                "today": datetime.fromtimestamp(time.time(), ZoneInfo(settings["timezone"])).date().isoformat()}

    def restore_backup(self, payload):
        """Preserve a private rollback file before atomically replacing local data."""
        incoming = validate_backup(payload, directory=self.store.path)
        with self.lock:
            now = time.time()
            old = serialize_backup(self.store.export_snapshot(), now)
            path = self.store.path / ("before-restore-" + datetime.fromtimestamp(now, ZoneInfo("UTC")).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(6) + ".json")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(old)
                    output.flush()
                    os.fsync(output.fileno())
            except Exception:
                path.unlink(missing_ok=True)
                raise
            self.store.restore_snapshot(incoming)
            self.reset_screen_tracker()
            self.state, self.message, self.last_checked = "disabled", "数据已恢复，采集已暂停", None
            self._collector_provider = incoming["settings"]["provider"]
            self.collector_wake.set()
            with self.cache_lock:
                self.cache.clear()
        return {"ok": True, "rollback_path": str(path), "tracking_enabled": False}

    def save_manual_entries(self, entries):
        with self.lock:
            now = time.time()
            settings = self.store.settings()
            zone = ZoneInfo(settings["timezone"])
            today = datetime.fromtimestamp(now, zone).date().isoformat()
            active = self.active_tracking(now, settings)
            includes_tail = isinstance(entries, list) and any(isinstance(entry, dict) and entry.get("present_end") is not None for entry in entries)
            if includes_tail:
                # Recheck while holding the collector lock: a stale browser
                # snapshot must never write a manual tail over an active run.
                pauses = settings.get("manual_pauses", [])
                manually_paused = bool(pauses and pauses[-1]["end"] is None)
                scheduled_paused, _ = night_pause_state(now, settings)
                sleeping = self.system_sleeping or any(s["end"] is None for s in self.store.sleep_intervals())
                checked = self.last_checked
                confirmed_disconnected = (self.state == "disconnected" and checked is not None
                                          and 0 <= now - checked <= MAX_SAMPLE_GAP)
                unknown = (settings["tracking_enabled"] and not manually_paused and not scheduled_paused
                           and not confirmed_disconnected)
                if active or sleeping or unknown or not self.power_events.empty():
                    raise ValueError("自动记录状态已变化，请重新检查工作历史；草稿仍在")
            if active and isinstance(entries, list):
                previous = next((e for e in self.store.manual_entries() if e["date"] == today), None)
                for entry in entries:
                    if not isinstance(entry, dict) or entry.get("date") != today:
                        continue
                    if previous and previous["kind"] == "intervals_override" and entry.get("kind") != "intervals_override":
                        raise ValueError("当前连接仍在记录，请先撤销当天修正，再使用补充")
                    if entry.get("kind") == "intervals_override":
                        cutoff = entry.get("edit_cutoff")
                        if type(cutoff) is int and cutoff > active["locked_from_ts"]:
                            raise ValueError("当前连接仍在记录，不能修正进行中的时段；请重新打开工作历史")
                        if previous and previous["kind"] == "intervals_override" and (previous.get("edit_cutoff") is None or previous["edit_cutoff"] > active["locked_from_ts"]):
                            raise ValueError("当前连接包含先前修正，请等待连接结束后再修改")
            def check_power_before_commit():
                if not self.power_events.empty():
                    raise ValueError("自动记录状态已变化，请重新检查工作历史；草稿仍在")
            if includes_tail:
                self.store.save_manual_entries(entries, now=now, precommit=check_power_before_commit)
            else:
                self.store.save_manual_entries(entries, now=now)
            with self.cache_lock:
                self.cache.clear()
            return self.manual_entries()

    def delete_manual_entry(self, day):
        with self.lock:
            self.store.delete_manual_entry(day)
            with self.cache_lock:
                self.cache.clear()
            return self.manual_entries()

    def verify_vpn(self, body):
        service_id, expected = body.get("service_id", ""), body.get("expected_state")
        if not isinstance(service_id, str) or not vpn.UUID.fullmatch(service_id) or expected not in ("connected", "disconnected"):
            raise ValueError("请选择系统服务及需要核对的状态")
        with self.lock:
            try:
                state, _ = self.detector({"provider": "system", "service_id": service_id, "tracking_enabled": True})
            except Exception:
                state = "unknown"
            if state != expected:
                revoked = self.store.invalidate_verification(service_id)
                message = "状态不匹配或无法读取，旧核对结果已清除；请重新核对连接和断开两种状态。"
                if revoked["tracking_paused"]:
                    message = "自动计时已暂停。" + message
                    self.state, self.message, self.last_checked = "disabled", message, None
                    self.log_collector()
                self.sync()
                return {"state": state, **revoked, "message": message}
            verified = self.store.verify_state(service_id, state)
            return {"state": state, **verified, "tracking_paused": False,
                    "message": "两种状态已核对，可以保存并启用计时。" if verified["verified"] else "此状态核对通过，请在 VPN 正常切换后再核对另一种状态。"}

    def run(self):
        # Explicit unknown boundary prevents backfilling the previous application's downtime.
        try:
            if self.store.settings()["tracking_enabled"]:
                self.store.record(time.time(), "unknown")
        except Exception:
            self.state, self.message = "unknown", "本机记录不可用"
        self.safe_sample()
        try:
            self.sync()
        except Exception:
            self.state, self.message = "unknown", "本机同步不可用"
        while not self.stop_event.is_set():
            self.collector_wake.wait(POLL_SECONDS)
            self.collector_wake.clear()
            if self.stop_event.is_set():
                break
            power_changed = False
            try:
                power_changed = self.process_power_events()
                power_changed = self.recover_power_monitor() or power_changed
            except Exception:
                self.power_error = "系统睡眠记录暂不可用；未确认的睡眠工时不做估算"
            if not self.system_sleeping:
                self.safe_sample()
            if power_changed or time.monotonic() >= self.next_sync_mono:
                try:
                    self.sync()
                except Exception:
                    with self.lock:
                        self.state, self.message = "unknown", "本机同步失败；请检查磁盘空间和数据目录权限"

    def safe_sample(self):
        try:
            self.sample()
        except Exception:
            with self.lock:
                self.state, self.message = "unknown", "记录暂不可用；请检查磁盘空间和数据目录权限"
                self._safely_end_screen_candidate()
                self.log_collector()

    def start(self):
        self.store.abandon_open_sleep()
        self.power_monitor.start()
        self.thread = threading.Thread(target=self.run, name="local-vpn-observer", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.collector_wake.set()
        self.power_monitor.stop()
        if self.thread:
            self.thread.join(timeout=7)
        with self.lock:
            self._safely_end_screen_candidate()
            self.store.abandon_open_sleep()
            if self.store.settings()["tracking_enabled"]:
                self.store.record(time.time(), "unknown")
            self.store.sync()
            self.store.close()

    def demo(self, now, timezone):
        """Deterministic synthetic observations, held only in memory, never in the DB."""
        tz = ZoneInfo(timezone)
        current = datetime.fromtimestamp(now, tz)
        key = (current.date(), timezone)
        if self.demo_key == key:
            return self.demo_samples
        first = current.date() - timedelta(days=84)
        result = []
        for offset in range(85):
            day = first + timedelta(days=offset)
            # An intentional two-day coverage gap, not fake vacation.
            if offset in (29, 30):
                continue
            start = datetime(day.year, day.month, day.day, tzinfo=tz)
            finish = start + timedelta(days=1)
            stamp, stop = start.timestamp(), finish.timestamp()
            end_hour = 16.7 + ((offset * 7) % 17) / 10
            while stamp <= stop:
                local = datetime.fromtimestamp(stamp, tz)
                hour = local.hour + local.minute / 60 + local.second / 3600
                if day.weekday() < 5:
                    working = 8.7 <= hour < end_hour or (offset % 4 == 0 and 20.2 <= hour < 21.1)
                else:
                    working = offset % 3 == 0 and 14 <= hour < 16.1
                result.append({"ts": stamp, "state": "connected" if working else "disconnected"})
                stamp += 30
        self.demo_key, self.demo_samples = key, result
        return result

    def dashboard(self, period, demo=False):
        now = time.time()
        settings = self.store.settings()
        sync = self.store.sync_status()
        manual = [] if demo else self.store.manual_entries()
        sleeps = [] if demo else self.store.sleep_intervals(now - 370 * 86400)
        key = (period, demo, sync["published_seq"], int(now // 60), json.dumps(settings, sort_keys=True),
               json.dumps(manual, sort_keys=True), json.dumps(sleeps, sort_keys=True))
        with self.cache_lock:
            summary = self.cache.get(key)
        if summary is None:
            if demo:
                sample_settings = dict(settings, annual_salary=180000, salary_history=[], theoretical_daily_hours=8, pause_on_sleep=True, work_start="09:00", work_end="17:00", workdays=[0, 1, 2, 3, 4], manual_pauses=[])
                samples = self.demo(now, settings["timezone"])
            else:
                sample_settings = settings
                # 370 days retains a boundary observation for all supported periods.
                samples = self.store.published_samples(now - 370 * 86400)
            summary = summarize(samples, sample_settings, period, now, manual_entries=manual, sleep_intervals=sleeps)
            with self.cache_lock:
                if len(self.cache) > 20:
                    self.cache.clear()
                self.cache[key] = summary
        with self.lock:
            stale = settings["tracking_enabled"] and (self.last_checked is None or now - self.last_checked > 45)
            collector = {"state": "unknown" if stale else self.state,
                         "message": "采集状态已过期；缺口不会继续计时" if stale else self.message,
                         "night_paused": night_pause_state(now, settings)[0],
                         "manual_paused": bool(settings["manual_pauses"] and settings["manual_pauses"][-1]["end"] is None),
                         "last_checked_at": iso(self.last_checked),
                         "last_synced_at": iso(sync["last_synced_at"]),
                         "next_sync_at": iso(self.next_sync), "pending_count": sync["pending_count"]}
        return {"mode": "demo" if demo else "live", "summary": summary, "settings": settings,
                "vpn_verification": self.store.verification(settings["service_id"]),
                "demo_salary": 180000 if demo else None, "collector": collector, "power_monitor": self.power_status(),
                "screen_monitor": ({"available": False, "message": "演示模式不读取真实屏幕状态。"} if demo else self.screen_monitor_state),
                "screen_alerts": ([] if demo else self.screen_alerts(settings)),
                "privacy": {"storage_path": str(self.store.path), "sync_target": "仅此 Mac（127.0.0.1）",
                            "external_upload": False}, "csrf_token": self.token}

    def history_month(self, month):
        settings = self.store.settings()
        if len(month) != 7 or month[4] != '-' or not (month[:4] + month[5:]).isdigit():
            raise ValueError("请选择有效月份")
        first = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        now = time.time()
        zone = ZoneInfo(settings['timezone'])
        today = datetime.fromtimestamp(now, zone).date()
        if first > today.replace(day=1) or first.year == 9999:
            raise ValueError("请选择今天或之前的月份")
        next_first = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
        start = datetime(first.year, first.month, 1, tzinfo=zone).timestamp()
        end = min(now, datetime(next_first.year, next_first.month, 1, tzinfo=zone).timestamp() + 45)
        return {"days": calendar_month(self.store.published_samples(start - 45, end), settings, first, now,
                                       self.store.manual_entries(), self.store.sleep_intervals(start)),
                "month": month}

    def active_tracking(self, now, settings):
        """Return only the current, freshly confirmed connected run, never extrapolated."""
        checked = self.last_checked
        if (not settings["tracking_enabled"] or self.state != "connected" or self.system_sleeping
                or not self.power_events.empty() or checked is None or not 0 <= now - checked <= MAX_SAMPLE_GAP):
            return None
        pauses = settings.get("manual_pauses", [])
        if pauses and pauses[-1]["end"] is None:
            return None
        # VPN is still sampled during a scheduled pause, but the interval is not
        # accumulating work and must remain editable. A fresh observation from
        # before the end of a pause does not prove post-pause tracking yet.
        paused, resumed = night_pause_state(now, settings)
        checked_paused, _ = night_pause_state(checked, settings)
        if paused or checked_paused:
            return None
        zone = ZoneInfo(settings["timezone"])
        today = datetime.fromtimestamp(now, zone).date()
        start = datetime.combine(today, datetime.min.time(), zone).timestamp()
        sleeps = self.store.sleep_intervals(start)
        if any(s["end"] is None for s in sleeps):
            return None
        wakes = [s["end"] for s in sleeps if s["end"] is not None and start <= s["end"] <= checked]
        pause_end = pauses[-1]["end"] if pauses and pauses[-1]["end"] is not None else start
        lower = max([start, pause_end, *wakes])
        samples = self.store.recent_samples(lower, now)
        if not samples or samples[0]["state"] != "connected" or samples[0]["ts"] != checked:
            return None
        current = checked
        for sample in samples[1:]:
            stamp = sample["ts"]
            if stamp == current:
                continue  # the later inserted observation wins at equal timestamps
            if sample["state"] != "connected" or current - stamp > MAX_SAMPLE_GAP:
                break
            current = stamp
        if resumed is not None:
            current = max(current, resumed)
        locked = max(start, int(current // 60) * 60)
        return {"start": datetime.fromtimestamp(current, zone).isoformat(),
                "last_confirmed": datetime.fromtimestamp(checked, zone).isoformat(),
                "locked_from": datetime.fromtimestamp(locked, zone).isoformat(), "locked_from_ts": locked}

    def history_day(self, day):
        try:
            parsed = date.fromisoformat(day)
        except (TypeError, ValueError):
            raise ValueError("请选择有效日期") from None
        settings = self.store.settings()
        zone = ZoneInfo(settings["timezone"])
        now = time.time()
        if parsed.isoformat() != day or parsed >= date.max or parsed > datetime.fromtimestamp(now, zone).date():
            raise ValueError("请选择今天或过去的日期")
        start = datetime.combine(parsed, datetime.min.time(), zone).timestamp()
        end = min(now, datetime.combine(parsed + timedelta(days=1), datetime.min.time(), zone).timestamp() + 45)
        with self.lock:
            sleeps = [s for s in self.store.sleep_intervals(start) if s["start"] < end]
            active = self.active_tracking(now, settings) if parsed == datetime.fromtimestamp(now, zone).date() else None
            manual = self.store.manual_entries()
            result = history_day(self.store.published_samples(start - 45, end), settings, parsed, now,
                                 manual, sleeps, self.store.sync_status()['pending_count'],
                                 active["locked_from_ts"] if active else None)
            if active:
                previous = next((e for e in manual if e["date"] == day), None)
                active["save_blocked"] = bool(previous and previous["kind"] == "intervals_override" and
                    (previous.get("edit_cutoff") is None or previous["edit_cutoff"] > active["locked_from_ts"]))
                if active["save_blocked"]:
                    active["message"] = "当前连接包含先前修正，为保留已有调整，请在连接结束后重新打开工作历史再修改。"
                active.pop("locked_from_ts")
            result["active_tracking"] = active
            result["edit_revision"] = self.store.manual_revision(day)
            # Allows a newly loaded frontend to detect a still-running older
            # service before attempting the backwards-compatible tail request.
            result["present_manual_tail_supported"] = True
            return result


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HourlyLocal/0.1"
        sys_version = ""

        def log_message(self, *_):
            # Avoid keeping salaries, service identifiers or query parameters in access logs.
            pass

        def allowed_host(self):
            port = self.server.server_address[1]
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def session_cookie_name(self):
            return f"hourly_session_{self.server.server_address[1]}"

        @staticmethod
        def token_matches(candidate, expected):
            return secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))

        def valid_session_cookie(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except CookieError:
                return False
            value = cookie.get(self.session_cookie_name())
            return value is not None and self.token_matches(value.value, app.session_token)

        def authenticated(self):
            # A tab can retain an old header after another tab renews the session.
            # Either current credential is sufficient; neither bypasses POST checks.
            return (self.token_matches(self.headers.get("X-Session-Token", ""), app.session_token)
                    or self.valid_session_cookie()
                    or app.browser_grants.verify(self.headers.get("X-Browser-Token", "")))

        def reply(self, status, data, content_type="application/json; charset=utf-8", download=None):
            is_file = isinstance(data, Path)
            if not is_file and not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(data.stat().st_size if is_file else len(data)))
            if download:
                self.send_header("Content-Disposition", 'attachment; filename="' + download + '"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
            route = urlsplit(self.path).path
            if (200 <= status < 300 and route.startswith("/api/") and route != "/api/health"
                    and self.allowed_host()
                    and (self.token_matches(self.headers.get("X-Session-Token", ""), app.session_token)
                         or app.browser_grants.verify(self.headers.get("X-Browser-Token", "")))
                    and not self.valid_session_cookie()):
                # HTTP loopback cannot use Secure. HttpOnly keeps the credential out
                # of JS, and the port suffix prevents unrelated local apps' collisions.
                self.send_header("Set-Cookie", f"{self.session_cookie_name()}={app.session_token}; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            if is_file:
                with data.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        self.wfile.write(chunk)
            else:
                self.wfile.write(data)

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {"error": "仅允许本机访问"})
            path = urlsplit(self.path)
            if path.path.startswith("/api/") and path.path != "/api/health" and not self.authenticated():
                return self.reply(401, {"error": "请通过 start-hourly-rate.command 重新打开本机入口"})
            if path.path == "/api/session":
                return self.reply(200, {"csrf_token": app.token})
            if path.path == "/api/autostart":
                return self.reply(200, LoginItem(app.store.path, self.server.server_address[1]).status())
            if path.path == "/api/manual-entries":
                return self.reply(200, app.manual_entries())
            if path.path == "/api/export":
                format_name = parse_qs(path.query).get("format", [""])[0]
                if format_name not in ("json", "csv", "sqlite"):
                    return self.reply(400, {"error": "请选择 JSON、CSV 或 SQLite 导出格式"})
                try:
                    if format_name == "sqlite":
                        with app.lock:
                            path = snapshot_file(app.store)
                        try:
                            return self.reply(200, path, "application/vnd.sqlite3", "hourly-rate-backup.sqlite3")
                        finally:
                            path.unlink(missing_ok=True)
                    with app.lock:
                        snapshot, now = app.store.export_snapshot(), time.time()
                    if format_name == "json":
                        return self.reply(200, serialize_backup(snapshot, now), download="hourly-rate-backup.json")
                    return self.reply(200, csv_daily(snapshot, now), "text/csv; charset=utf-8", "hourly-rate-daily.csv")
                except BackupTooLarge as error:
                    return self.reply(413, {"error": str(error)})
                except (OSError, ValueError, OverflowError, sqlite3.Error):
                    return self.reply(500, {"error": "无法生成导出文件；原始数据未更改"})
            if path.path == "/api/history-month":
                try:
                    return self.reply(200, app.history_month(parse_qs(path.query).get("month", [""])[0]))
                except (ValueError, OverflowError):
                    return self.reply(400, {"error": "请选择有效的过去或当前月份"})
            if path.path == "/api/history-day":
                try:
                    return self.reply(200, app.history_day(parse_qs(path.query).get("date", [""])[0]))
                except (ValueError, OverflowError):
                    return self.reply(400, {"error": "请选择有效的过去或当前日期"})
            if path.path == "/api/dashboard":
                query = parse_qs(path.query)
                period = query.get("period", ["week"])[0]
                if period not in PERIODS:
                    return self.reply(400, {"error": "不支持的统计周期"})
                try:
                    return self.reply(200, app.dashboard(period, query.get("demo", ["0"])[0] == "1"))
                except Exception:
                    return self.reply(500, {"error": "本机汇总失败；原始记录仍保存在本机"})
            if path.path == "/api/vpn-services":
                return self.reply(200, vpn.discover())
            if path.path == "/api/script-status":
                return self.reply(200, app.check_script())
            if path.path == "/api/status-log":
                try:
                    return self.reply(200, app.status_log())
                except OSError:
                    return self.reply(500, {"error": "暂时无法读取本机状态日志"})
            if path.path == "/api/health":
                return self.reply(200, {"ok": True, "app": "hourly-rate-local", "external_upload": False})
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/index.html": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
                      "/dashboard-translations.js": ("dashboard-translations.js", "text/javascript; charset=utf-8"),
                      "/manual.js": ("manual.js", "text/javascript; charset=utf-8"),
                      "/draft-undo.js": ("draft-undo.js", "text/javascript; charset=utf-8"),
                      "/history-calendar.js": ("history-calendar.js", "text/javascript; charset=utf-8"),
                      "/manual.css": ("manual.css", "text/css; charset=utf-8"),
                      "/timeline.css": ("timeline.css", "text/css; charset=utf-8"),
                      "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
                      "/logs.html": ("logs.html", "text/html; charset=utf-8"),
                      "/logs.js": ("logs.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path.path in static:
                filename, kind = static[path.path]
                try:
                    return self.reply(200, (ROOT / "static" / filename).read_bytes(), kind)
                except FileNotFoundError:
                    return self.reply(503, {"error": "界面文件尚未就绪"})
            return self.reply(404, {"error": "没有此页面"})

        def do_POST(self):
            port = self.server.server_address[1]
            origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            origin = self.headers.get("Origin")
            if (not self.allowed_host() or (origin is not None and origin not in origins)
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    or not self.authenticated()
                    or not self.token_matches(self.headers.get("X-CSRF-Token", ""), app.token)):
                return self.reply(403, {"error": "请求未通过本机验证，请刷新页面后重试"})
            route = urlsplit(self.path).path
            binary = route == "/api/restore-sqlite"
            if self.headers.get_content_type() != ("application/vnd.sqlite3" if binary else "application/json") or self.headers.get("Transfer-Encoding"):
                return self.reply(415, {"error": "请求格式无效"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = MAX_SQLITE_BYTES if binary else MAX_RESTORE_BYTES if route == "/api/restore" else 262144 if route == "/api/manual-entries" else 16384
                if not 0 < length <= limit:
                    return self.reply(413, {"error": "请求大小无效"})
                if binary:
                    fd, name = tempfile.mkstemp(prefix="restore-upload-", suffix=".sqlite3", dir=app.store.path)
                    uploaded = Path(name)
                    try:
                        with os.fdopen(fd, "wb") as output:
                            remaining = length
                            while remaining:
                                chunk = self.rfile.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise ValueError("备份文件不完整")
                                output.write(chunk)
                                remaining -= len(chunk)
                        try:
                            return self.reply(200, restore_sqlite_file(app, uploaded))
                        except (ValueError, TypeError, KeyError, OverflowError, sqlite3.DatabaseError) as error:
                            return self.reply(400, {"error": str(error) or "SQLite 备份无效"})
                        except OSError:
                            return self.reply(500, {"error": "无法创建回滚备份或恢复数据"})
                    finally:
                        uploaded.unlink(missing_ok=True)
                raw_body = self.rfile.read(length)
                if route == "/api/restore":
                    try:
                        body = json.loads(raw_body, object_pairs_hook=_unique_json_object, parse_constant=_reject_json_constant)
                    except (ValueError, UnicodeError):
                        return self.reply(400, {"error": "备份不是有效 JSON，或包含重复字段及无效数值"})
                else:
                    body = json.loads(raw_body)
                if not isinstance(body, dict):
                    raise ValueError("请求应为对象")
                if route in ("/api/browser-auth/pair", "/api/browser-auth/extend", "/api/browser-auth/revoke-all"):
                    if (route.endswith("/pair") and set(body) != {"pair_token"}) or (not route.endswith("/pair") and body):
                        return self.reply(400, {"error": "无效的授权请求"})
                    with app.auth_lock:
                        # Recheck under the lock so requests validated before a
                        # revocation cannot create a grant after it completes.
                        if not self.authenticated() or not self.token_matches(self.headers.get("X-CSRF-Token", ""), app.token):
                            return self.reply(403, {"error": "授权已失效，请重新打开本机入口"})
                        try:
                            if route.endswith("/extend"):
                                expiry = app.browser_grants.extend(self.headers.get("X-Browser-Token", ""))
                                if expiry is None:
                                    return self.reply(403, {"error": "此浏览器的授权已过期或撤销，请重新通过本机入口授权"})
                                return self.reply(200, {"expires_at": expiry})
                            if route.endswith("/pair"):
                                pair_token = body.get("pair_token")
                                if not isinstance(pair_token, str) or not self.token_matches(pair_token, app.pair_token):
                                    return self.reply(403, {"error": "启动授权已失效，请重新打开本机入口"})
                                next_pair = secrets.token_urlsafe(32)
                                access_path = app.store.path / "access.json"
                                port = self.server.server_address[1]
                                old_access = {"port": port, "session_token": app.session_token, "pair_token": app.pair_token}
                                write_private_json(access_path, {**old_access, "pair_token": next_pair})
                                try:
                                    credential, expiry = app.browser_grants.issue()
                                except (OSError, ValueError, UnicodeError):
                                    write_private_json(access_path, old_access)
                                    raise
                                app.pair_token = next_pair
                                return self.reply(200, {"browser_token": credential, "expires_at": expiry})
                            old_session = app.session_token
                            old_pair = app.pair_token
                            new_session = secrets.token_urlsafe(32)
                            new_csrf = secrets.token_urlsafe(32)
                            new_pair = secrets.token_urlsafe(32)
                            access_path = app.store.path / "access.json"
                            port = self.server.server_address[1]
                            write_private_json(access_path, {"port": port, "session_token": new_session, "pair_token": new_pair})
                            try:
                                app.browser_grants.clear()
                            except (OSError, ValueError, UnicodeError):
                                write_private_json(access_path, {"port": port, "session_token": old_session, "pair_token": old_pair})
                                raise
                            app.session_token, app.token, app.pair_token = new_session, new_csrf, new_pair
                            return self.reply(200, {"ok": True})
                        except (OSError, ValueError, UnicodeError):
                            return self.reply(500, {"error": "无法更新本机授权，请检查数据目录权限"})
                if route == "/api/restore":
                    if set(body) != {"backup"}:
                        return self.reply(400, {"error": "请选择有效的 JSON 备份"})
                    try:
                        return self.reply(200, app.restore_backup(body["backup"]))
                    except (ValueError, TypeError, KeyError, OverflowError) as error:
                        return self.reply(400, {"error": str(error) or "备份格式无效"})
                    except (OSError, sqlite3.Error):
                        return self.reply(500, {"error": "无法创建本机回滚备份或恢复数据；请检查剩余空间后重试"})
                if route in ("/api/manual-entries", "/api/manual-entries/delete"):
                    try:
                        if route == "/api/manual-entries":
                            if set(body) != {"entries"}:
                                raise ValueError("请提供要保存的补录记录")
                            return self.reply(200, app.save_manual_entries(body["entries"]))
                        if set(body) != {"date"}:
                            raise ValueError("请提供要撤销的补录日期")
                        return self.reply(200, app.delete_manual_entry(body["date"]))
                    except ValueError as error:
                        return self.reply(400, {"error": str(error)})
                if route == "/api/settings":
                    return self.reply(200, {"settings": app.settings(body)})
                if route == "/api/manual-pause":
                    if set(body) != {"paused"} or type(body["paused"]) is not bool:
                        return self.reply(400, {"error": "请选择暂停或恢复计时"})
                    try:
                        return self.reply(200, app.set_manual_pause(body["paused"]))
                    except ValueError as error:
                        return self.reply(400, {"error": str(error)})
                if route == "/api/screen-alert/keep":
                    if set(body) != {"id"}:
                        return self.reply(400, {"error": "请选择有效的提醒"})
                    try:
                        return self.reply(200, app.keep_screen_alert(body["id"]))
                    except ValueError as error:
                        return self.reply(400, {"error": str(error)})
                if route == "/api/autostart":
                    if set(body) != {"enabled"} or type(body["enabled"]) is not bool:
                        return self.reply(400, {"error": "请选择开启或关闭登录后启动。"})
                    try:
                        return self.reply(200, LoginItem(app.store.path, self.server.server_address[1]).set_enabled(body["enabled"]))
                    except (AutostartError, OSError) as error:
                        return self.reply(500, {"error": str(error) if isinstance(error, AutostartError) else "无法修改本机登录项，请检查权限。"})
                if route == "/api/verify-vpn":
                    return self.reply(200, app.verify_vpn(body))
                if route == "/api/sync":
                    app.sync()
                    return self.reply(200, {"ok": True, "external_upload": False})
                if route == "/api/stop":
                    self.reply(200, {"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                return self.reply(404, {"error": "没有此操作"})
            except (ValueError, UnicodeError, TypeError):
                return self.reply(400, {"error": "设置无效，请检查年薪、时间、时区及 VPN 配置"})

        def do_OPTIONS(self):
            self.reply(403, {"error": "不接受跨站请求"})

    return Handler


def _login_log_stream(directory):
    """Open the common service log in append mode, without following symlinks."""
    path = Path(directory) / "service.log"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        return os.fdopen(fd, "a", encoding="utf-8", buffering=1)
    except BaseException:
        os.close(fd)
        raise


def main():
    parser = argparse.ArgumentParser(description="时薪温度计 · 仅在此 Mac 保存和处理数据")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("invalid port")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%Y-%m-%dT%H:%M:%S%z")
    os.umask(0o077)
    try:
        # Both the directory lock and listening socket precede any SQLite access.
        # A rejected start must not append observations or publish pending rows.
        with InstanceLock(args.data_dir) as instance:
            login_log = None
            if os.environ.get("HOURLY_RATE_LOGIN_ITEM") == "1":
                # launchd's diagnostic output is separate; status events append
                # to the same persistent log as manually launched sessions.
                login_log = _login_log_stream(instance.directory)
                logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                                    datefmt="%Y-%m-%dT%H:%M:%S%z", stream=login_log, force=True)
            try:
                server = LocalServer(("127.0.0.1", args.port), BaseHTTPRequestHandler)
            except OSError as error:
                if error.errno == errno.EADDRINUSE:
                    raise SystemExit("本机端口已占用；没有修改记录。请关闭旧实例或指定其他端口。") from None
                raise SystemExit("无法启动本机监听；没有修改记录，请检查本机访问权限。") from None
            app = None
            started = False
            access_file = instance.directory / "access.json"
            temporary_access = instance.directory / "access.json.tmp"
            try:
                app = Application(instance.directory)
                server.RequestHandlerClass = handler_for(app)

                def stop(_signum, _frame):
                    # shutdown() waits for serve_forever(), so never run it on
                    # this main thread, including a signal during startup.
                    threading.Thread(target=server.shutdown, daemon=True).start()

                signal.signal(signal.SIGTERM, stop)
                signal.signal(signal.SIGINT, stop)
                temporary_access.write_text(json.dumps({
                    "port": server.server_address[1], "session_token": app.session_token,
                    "pair_token": app.pair_token
                }), encoding="utf-8")
                temporary_access.chmod(0o600)
                temporary_access.replace(access_file)
                app.start()
                started = True
                print(f"本机仪表盘：http://127.0.0.1:{server.server_address[1]}/", flush=True)
                print("数据只保存在本机；未配置 VPN 前不会采集。关闭服务会停止后台记录。", flush=True)
                server.serve_forever(poll_interval=0.25)
            finally:
                server.server_close()
                try:
                    if app is not None:
                        if started:
                            app.close()
                        else:
                            # Startup cleanup must not record a stop boundary.
                            app.store.close()
                finally:
                    temporary_access.unlink(missing_ok=True)
                    if app is not None:
                        try:
                            if json.loads(access_file.read_text()).get("session_token") == app.session_token:
                                access_file.unlink(missing_ok=True)
                        except (OSError, ValueError):
                            pass
            # Keep the lock until the database and access file are both closed.
            if login_log is not None:
                logging.shutdown()
                login_log.close()
    except AlreadyRunning:
        raise SystemExit("此数据目录已有服务正在运行或启动；没有修改记录。请使用 start-hourly-rate.command 打开已有服务。") from None


if __name__ == "__main__":
    main()
