"""Pure, local calculations for VPN-based work-time observations.

No network, files, or platform APIs are used here. A connection is a chosen
accounting signal, not proof of attention or of work performed. Missing samples
are never treated as either working or resting.
"""

from __future__ import annotations

import math
import time
from bisect import bisect_left, bisect_right
from calendar import monthrange
from datetime import date, datetime, time as daytime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo


MAX_SAMPLE_GAP = 45.0
VALID_STATES = frozenset({"connected", "disconnected", "unknown"})
PERIOD_LABELS = {
    "today": "今天",
    "week": "本周",
    "month": "本月",
    "quarter": "本季度",
    "half": "本半年",
    "year": "今年 · YTD",
    "rolling_year": "过去 365 天",
}


def _clock(value: str) -> daytime:
    try:
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError
        hour, minute = (int(part) for part in value.split(":"))
        return daytime(hour, minute)
    except (TypeError, ValueError) as exc:
        raise ValueError("工作时间必须是 HH:MM 格式") from exc


def validate_salary_amount(salary, optional=False):
    if optional and salary is None:
        return None
    if (isinstance(salary, bool) or not isinstance(salary, (int, float))
            or not 0 < salary <= 1e10 or not math.isfinite(salary)):
        raise ValueError("年薪应为大于零且不超过 100 亿的数字")
    return salary


def validate_theoretical_daily_hours(hours):
    if (isinstance(hours, bool) or not isinstance(hours, (int, float))
            or not 0 < hours <= 24 or not math.isfinite(hours)):
        raise ValueError("理论每日工时应为大于零且不超过 24 的数字")
    return hours


def validate_salary_history(history):
    """Return independent, date-ordered salary changes with strict ISO dates."""
    if not isinstance(history, list):
        raise ValueError("薪资历史应为列表")
    result, seen = [], set()
    for entry in history:
        if not isinstance(entry, dict) or set(entry) != {"effective_from", "annual_salary"}:
            raise ValueError("每条薪资历史须包含生效日期与年薪")
        effective = entry["effective_from"]
        try:
            if not isinstance(effective, str) or date.fromisoformat(effective).isoformat() != effective:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("薪资生效日期应为有效的 YYYY-MM-DD 日期") from None
        if effective in seen:
            raise ValueError("同一天只能设置一条薪资")
        seen.add(effective)
        result.append({"effective_from": effective,
                       "annual_salary": validate_salary_amount(entry["annual_salary"])})
    return sorted(result, key=lambda entry: entry["effective_from"])


def _configuration(settings: dict) -> dict:
    zone = ZoneInfo(settings.get("timezone", "America/Los_Angeles"))
    start = _clock(settings.get("work_start", "09:00"))
    end = _clock(settings.get("work_end", "17:00"))
    if end <= start:
        raise ValueError("第一版需要同一天内的排班，结束时间须晚于开始时间")
    weekdays = settings.get("workdays", [0, 1, 2, 3, 4])
    if (
        not isinstance(weekdays, (list, tuple, set))
        or not weekdays
        or any(type(day) is not int or day < 0 or day > 6 for day in weekdays)
    ):
        raise ValueError("工作日必须是 0（周一）到 6（周日）之间的非空列表")
    salary = validate_salary_amount(settings.get("annual_salary"), optional=True)
    theoretical_hours = validate_theoretical_daily_hours(settings.get("theoretical_daily_hours", 8))
    history = validate_salary_history(settings.get("salary_history", []))
    pause_on_sleep = settings.get("pause_on_sleep", True)
    if type(pause_on_sleep) is not bool:
        raise ValueError("无效的睡眠计时开关")
    night_pause_enabled = settings.get("night_pause_enabled", False)
    if type(night_pause_enabled) is not bool:
        raise ValueError("无效的夜间暂停开关")
    night_pause_start = _clock(settings.get("night_pause_start", "00:00"))
    night_pause_end = _clock(settings.get("night_pause_end", "09:00"))
    if night_pause_start == night_pause_end:
        raise ValueError("夜间暂停的开始和结束时间不能相同")
    return {
        "zone": zone,
        "start": start,
        "end": end,
        "weekdays": frozenset(weekdays),
        "salary": salary,
        "theoretical_daily_hours": theoretical_hours,
        "pause_on_sleep": pause_on_sleep,
        "night_pause_enabled": night_pause_enabled,
        "night_pause_start": night_pause_start,
        "night_pause_end": night_pause_end,
        "salary_dates": [date.fromisoformat(entry["effective_from"]) for entry in history],
        "salary_values": [entry["annual_salary"] for entry in history],
    }


def _salary_on(day: date, config: dict):
    index = bisect_right(config["salary_dates"], day) - 1
    return config["salary_values"][index] if index >= 0 else config["salary"]


def _midnight(day: date, zone: ZoneInfo) -> float:
    return datetime.combine(day, daytime(), zone).timestamp()


def _dates(start: date, end_exclusive: date):
    while start < end_exclusive:
        yield start
        start += timedelta(days=1)


def _shift_months(day: date, months: int) -> date:
    """Keep the calendar day when possible, clamping short destination months."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _schedule(day: date, config: dict) -> tuple[float, float] | None:
    if day.weekday() not in config["weekdays"]:
        return None
    zone = config["zone"]
    start = datetime.combine(day, config["start"], zone).timestamp()
    end = datetime.combine(day, config["end"], zone).timestamp()
    # A DST transition can make an unusual wall-clock schedule empty. Keep it
    # empty, never invent or subtract actual seconds for that occurrence.
    return start, max(start, end)


def _annual_workdays(year: int, config: dict) -> int:
    return sum(day.weekday() in config["weekdays"]
               for day in _dates(date(year, 1, 1), date(year + 1, 1, 1)))


def _daily_income(day: date, observed: float, config: dict, annual_days: dict):
    """Credit a recorded workday once, independently of clock-time overlap."""
    if observed <= 0 or day.weekday() not in config["weekdays"]:
        return 0.0
    salary = _salary_on(day, config)
    if salary is None:
        return None
    if day.year not in annual_days:
        annual_days[day.year] = _annual_workdays(day.year, config)
    return salary / annual_days[day.year]


def _rate_floor_applied(income, work_seconds):
    """An hourly-rate estimate, never a modification of observed work."""
    return income is not None and 0 < work_seconds < 3600


def _actual_rate(income, work_seconds, *, minimum_hour=False):
    if income is None:
        return "missing_salary", None
    if work_seconds <= 0:
        return "no_work", None
    denominator = max(work_seconds, 3600) if minimum_hour else work_seconds
    return "ready", income / (denominator / 3600)


def _period_start(period: str, now: float, zone: ZoneInfo) -> float:
    today = datetime.fromtimestamp(now, zone).date()
    if period == "today":
        day = today
    elif period == "week":
        day = today - timedelta(days=today.weekday())
    elif period == "month":
        day = today.replace(day=1)
    elif period == "quarter":
        day = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)
    elif period == "half":
        day = today.replace(month=1 if today.month <= 6 else 7, day=1)
    elif period == "year":
        day = today.replace(month=1, day=1)
    elif period == "rolling_year":
        return now - 365 * 24 * 60 * 60
    else:
        raise ValueError("不支持的统计范围")
    return _midnight(day, zone)


def _previous_period(period: str, today: date, config: dict):
    """Return a previous complete local-calendar period, never a guessed date."""
    if period == "today":
        previous = today - timedelta(days=1)
        while previous.weekday() not in config["weekdays"]:
            previous -= timedelta(days=1)
        return previous, previous + timedelta(days=1), "上一个工作日"
    if period == "week":
        end = today - timedelta(days=today.weekday())
        return end - timedelta(days=7), end, "上周"
    if period == "month":
        end = today.replace(day=1)
        return _shift_months(end, -1), end, "上月"
    return None


def _period_comparison(period, now, config, segments, manual, current_rate):
    """Compare the current rate with a complete previous local-calendar period.

    Use the same observed-work and salary rules as the headline. The previous
    period's boundaries are local midnights, so DST and salary changes are not
    approximated as a fixed number of seconds.
    """
    zone = config["zone"]
    today = datetime.fromtimestamp(now, zone).date()
    bounds = _previous_period(period, today, config)
    if bounds is None:
        return None
    first, last, label = bounds
    start, end = _midnight(first, zone), _midnight(last, zone)
    known = _known_by_day(segments, start, end, config)
    previous_manual = _manual_in_window(manual, start, end, config)
    _apply_estimates(known, previous_manual)
    work = sum(entry["work"] for entry in known.values())
    recorded = sum(_recorded(entry) for entry in known.values())
    annual_days = {}
    incomes = [_daily_income(day, _recorded(entry), config, annual_days)
               for day, entry in known.items()]
    income = None if any(value is None for value in incomes) else sum(incomes)
    status, previous_rate = _actual_rate(income, work, minimum_hour=period == "today")
    if not recorded:
        status, previous_rate = "no_records", None
    percent = ((current_rate / previous_rate - 1) * 100
               if current_rate is not None and previous_rate is not None and previous_rate > 0
               else None)
    return {"label": label, "start": first.isoformat(), "end_exclusive": last.isoformat(),
            "actual_rate": previous_rate, "rate_status": status,
            "rate_floor_applied": period == "today" and _rate_floor_applied(income, work),
            "delta_percent": percent, "recorded_days": recorded,
            "period_days": (last - first).days}


def _segments(samples: Iterable[dict], now: float) -> list[tuple[float, float, str]]:
    """Normalize duplicates and merge contiguous equal states in one pass.

    A later observation at the same timestamp replaces an earlier one. Samples
    beyond ``now`` cannot establish past coverage in a retrospective summary.
    Long gaps are wholly unknown, and the last point is never extrapolated.
    """
    points = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        try:
            ts = float(sample["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(ts) or ts > now:
            continue
        state = sample.get("state", "unknown")
        if not isinstance(state, str) or state not in VALID_STATES:
            state = "unknown"
        points.append((ts, state))
    points.sort(key=lambda point: point[0])
    unique = []
    for point in points:
        if unique and unique[-1][0] == point[0]:
            unique[-1] = point
        else:
            unique.append(point)

    segments = []
    for previous, current in zip(unique, unique[1:]):
        start, state = previous
        end = current[0]
        if end - start > MAX_SAMPLE_GAP:
            state = "unknown"
        if segments and segments[-1][2] == state and segments[-1][1] == start:
            segments[-1] = (segments[-1][0], end, state)
        else:
            segments.append((start, end, state))
    return segments


def _overlap(a: float, b: float, x: float, y: float) -> float:
    return max(0.0, min(b, y) - max(a, x))


def _scheduled_seconds(start: float, end: float, config: dict) -> float:
    if end <= start:
        return 0.0
    zone = config["zone"]
    first = datetime.fromtimestamp(start, zone).date()
    last = datetime.fromtimestamp(end, zone).date() + timedelta(days=1)
    return sum(
        _overlap(start, end, *slot)
        for day in _dates(first, last)
        if (slot := _schedule(day, config)) is not None
    )


def _known_by_day(segments: list, start: float, end: float, config: dict) -> dict:
    """Split merged known intervals at local midnight; linear in segments/days."""
    zone = config["zone"]
    days = {}
    for segment in segments:
        begin, finish, state = segment[:3]
        if state == "unknown" or finish <= start:
            continue
        if begin >= end:
            break
        begin, finish = max(begin, start), min(finish, end)
        while begin < finish:
            day = datetime.fromtimestamp(begin, zone).date()
            boundary = _midnight(day + timedelta(days=1), zone)
            until = min(finish, boundary)
            entry = days.setdefault(day, {"work": 0.0, "observed": 0.0, "scheduled_observed": 0.0})
            seconds = until - begin
            if len(segment) > 3 and segment[3] == "sleep_estimate":
                entry["work"] += seconds
                entry["sleep_estimated"] = entry.get("sleep_estimated", 0.0) + seconds
                begin = until
                continue
            entry["observed"] += seconds
            if state == "connected":
                entry["work"] += seconds
            slot = _schedule(day, config)
            if slot is not None:
                entry["scheduled_observed"] += _overlap(begin, until, *slot)
            begin = until
    return days


def _merge_intervals(intervals):
    result = []
    for begin, finish in sorted(intervals):
        if finish <= begin:
            continue
        if result and begin <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], finish))
        else:
            result.append((begin, finish))
    return result


def _overlay_sleep(segments, entries, now, pause_on_sleep):
    """Overlay actual sleep events; ordinary sample gaps remain unknown.

    A completed sleep interval may use only a fresh pre-sleep connected sample.
    An open interval can suppress work but can never create estimated work.
    """
    if not entries:
        return segments
    sleeps = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        begin, end = entry.get("start"), entry.get("end")
        checked = entry.get("last_sample_ts")
        if (type(begin) not in (int, float) or not math.isfinite(begin)
                or (end is not None and (type(end) not in (int, float)
                    or not math.isfinite(end) or end < begin))):
            continue
        finish = min(now, end) if end is not None else now
        if begin >= finish:
            continue
        fresh = (type(checked) in (int, float) and math.isfinite(checked)
                 and 0 <= begin - checked <= MAX_SAMPLE_GAP)
        estimate = (not pause_on_sleep and end is not None and end <= now
                    and entry.get("state") == "connected" and fresh)
        state = "connected" if estimate else "unknown"
        source = "sleep_estimate" if estimate else ("sleep_paused" if pause_on_sleep else "sleep_unknown")
        sleeps.append((begin, finish, state, source))
    if not sleeps:
        return segments
    # Persistence yields disjoint intervals. Ignore malformed overlapping input
    # defensively, so it can neither double work nor overwrite later awake time.
    normalized = []
    for entry in sorted(set(sleeps)):
        if not normalized or entry[0] >= normalized[-1][1]:
            normalized.append(entry)
    points = sorted({point for begin, finish, *_ in segments for point in (begin, finish)}
                    | {point for begin, finish, *_ in normalized for point in (begin, finish)})
    result, raw_index, sleep_index = [], 0, 0
    for begin, finish in zip(points, points[1:]):
        while raw_index < len(segments) and segments[raw_index][1] <= begin:
            raw_index += 1
        while sleep_index < len(normalized) and normalized[sleep_index][1] <= begin:
            sleep_index += 1
        if sleep_index < len(normalized) and normalized[sleep_index][0] <= begin:
            state, source = normalized[sleep_index][2:]
        elif raw_index < len(segments) and segments[raw_index][0] <= begin:
            state = segments[raw_index][2]
            source = segments[raw_index][3] if len(segments[raw_index]) > 3 else "vpn"
        else:
            state, source = "unknown", "vpn"
        if result and result[-1][1] == begin and result[-1][2:] == (state, source):
            result[-1] = (result[-1][0], finish, state, source)
        else:
            result.append((begin, finish, state, source))
    return result


def _night_boundaries(start, end, config):
    """Find local-clock boundaries, including both sides of DST transitions.

    Each wall-clock boundary has up to two UTC instants (the repeated hour).
    Offset changes are also boundaries: a skipped or repeated wall-clock time
    can change whether an instant is paused even without crossing a configured
    start/end time.  Classification is performed on each resulting UTC span.
    """
    zone = config["zone"]
    first = datetime.fromtimestamp(start, zone).date() - timedelta(days=1)
    last = datetime.fromtimestamp(end, zone).date() + timedelta(days=2)
    boundaries = set()
    for day in _dates(first, last):
        for clock in (daytime(), config["night_pause_start"], config["night_pause_end"]):
            local = datetime.combine(day, clock, zone)
            for fold in (0, 1):
                point = local.replace(fold=fold).timestamp()
                if start < point < end:
                    boundaries.add(point)

    # Offset transitions in the IANA database are discrete instants. Sampling
    # one-hour brackets and bisecting changed brackets handles spring gaps and
    # both occurrences of fall-back hours without treating them as 24h days.
    def offset(stamp):
        return datetime.fromtimestamp(stamp, zone).utcoffset()

    left = math.floor(start)
    last_offset = offset(left)
    while left < end:
        right = min(left + 3600, math.ceil(end))
        right_offset = offset(right)
        if right_offset != last_offset:
            low, high = left, right
            while high - low > 1:
                middle = (low + high) // 2
                if offset(middle) == last_offset:
                    low = middle
                else:
                    high = middle
            if start < high < end:
                boundaries.add(float(high))
        left, last_offset = right, right_offset
    return sorted(boundaries)


def _night_paused_at(stamp, config):
    wall = datetime.fromtimestamp(stamp, config["zone"]).time()
    begin, end = config["night_pause_start"], config["night_pause_end"]
    return begin <= wall < end if begin < end else wall >= begin or wall < end


def night_pause_state(stamp, settings):
    """Return current pause status and today's most recent resume instant."""
    config = _configuration(settings)
    if not config["night_pause_enabled"]:
        return False, None
    today = datetime.fromtimestamp(stamp, config["zone"]).date()
    midnight = _midnight(today, config["zone"])
    resumed = None
    # Include exact-midnight and exact-now boundaries; only completed changes
    # can be used for the current automatic segment.
    for point in _night_boundaries(midnight - 1, stamp + 1, config):
        if midnight <= point <= stamp and _night_paused_at(point - .001, config) and not _night_paused_at(point, config):
            resumed = point
    return _night_paused_at(stamp, config), resumed


def _overlay_night(segments, config):
    """Pause automatic connected intervals without inventing observations.

    Unknown/disconnected VPN observations and paused/unknown sleep remain as
    they are.  The later manual overlay always has precedence over this policy.
    """
    if not config["night_pause_enabled"] or not segments:
        return segments
    connected = [part for part in segments if part[2] == "connected" and part[1] > part[0]]
    if not connected:
        return segments
    boundaries = _night_boundaries(connected[0][0], connected[-1][1], config)
    result = []
    for part in segments:
        begin, finish, state = part[:3]
        source = part[3] if len(part) > 3 else "vpn"
        first = bisect_right(boundaries, begin)
        last = bisect_left(boundaries, finish)
        points = [begin, *boundaries[first:last], finish] if state == "connected" else [begin, finish]
        for a, b in zip(points, points[1:]):
            if b <= a:
                continue
            paused = _night_paused_at((a + b) / 2, config)
            current = ("unknown", "night_paused") if state == "connected" and paused else (state, source)
            if result and result[-1][1] == a and result[-1][2:] == current:
                result[-1] = (result[-1][0], b, *current)
            else:
                result.append((a, b, *current))
    return result


def _manual_records(entries, now, config):
    """Normalize validated manual entries without altering caller-owned data."""
    if entries is None:
        return {}
    if not isinstance(entries, list):
        raise ValueError("手动记录应为列表")
    zone = config["zone"]
    today = datetime.fromtimestamp(now, zone).date()
    result, seen = {}, set()
    for original in entries:
        if not isinstance(original, dict):
            raise ValueError("手动记录应为对象")
        try:
            day = date.fromisoformat(original["date"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("无效的手动记录日期") from None
        if day.isoformat() != original["date"] or day in seen:
            raise ValueError("手动记录日期格式无效或重复")
        seen.add(day)
        # Defensive even for persisted entries: moving the clock or timezone
        # must never cause a future date or today's estimated total to count.
        if day > today:
            continue
        kind = original.get("kind")
        entry = {"date": day.isoformat(), "kind": kind, "note": original.get("note", "")}
        if kind == "intervals_override" and original.get("present_closed") is True:
            entry["present_closed"] = True
        if kind == "daily_total":
            if day >= today:
                continue
            hours = original.get("hours")
            if (isinstance(hours, bool) or not isinstance(hours, (int, float))
                    or not 0 <= hours <= 24 or not math.isfinite(hours)):
                raise ValueError("手动每日工时应在 0 到 24 小时之间")
            entry["hours"] = hours
        elif kind in ("intervals", "intervals_override"):
            cutoff = original.get("edit_cutoff") if kind == "intervals_override" else None
            if kind == "intervals_override" and day == today and cutoff is None:
                continue
            day_start, day_end = _midnight(day, zone), _midnight(day + timedelta(days=1), zone)
            if cutoff is not None and original.get("edit_cutoff_local") is not None:
                cutoff = datetime.combine(day, _clock(original["edit_cutoff_local"]), zone).timestamp()
            if cutoff is not None and (type(cutoff) not in (int, float) or not math.isfinite(cutoff)
                                       or not day_start <= cutoff <= day_end):
                raise ValueError("无效的修正截止时间")
            limit = min(day_end, cutoff) if cutoff is not None else day_end
            intervals, displayed = [], []
            for interval in original.get("intervals", []):
                begin = datetime.combine(day, _clock(interval["start"]), zone).timestamp()
                finish = (_midnight(day + timedelta(days=1), zone) if interval["end"] == "24:00"
                          else datetime.combine(day, _clock(interval["end"]), zone).timestamp())
                displayed.append({"start": interval["start"], "end": interval["end"]})
                if begin < min(finish, now, limit):
                    intervals.append((begin, min(finish, now, limit)))
            entry["intervals"] = displayed
            entry["_intervals"] = _merge_intervals(intervals)
            if kind == "intervals_override":
                entry["_override"] = (day_start, min(limit, now))
                if cutoff is not None:
                    entry["edit_cutoff"] = cutoff
                    tails = []
                    for interval in original.get("tail_intervals", []):
                        begin = datetime.combine(day, _clock(interval["start"]), zone).timestamp()
                        finish = (day_end if interval["end"] == "24:00"
                                  else datetime.combine(day, _clock(interval["end"]), zone).timestamp())
                        begin, finish = max(begin, cutoff), min(finish, now)
                        if begin < finish:
                            tails.append((begin, finish))
                    entry["_tail_intervals"] = _merge_intervals(tails)
        else:
            raise ValueError("不支持的手动记录类型")
        result[day] = entry
    return result


def _overlay_manual_pauses(segments, intervals, now):
    """Hide automatic work in explicit pause intervals; keep raw VPN samples."""
    if not intervals or not segments:
        return segments
    pauses = [(item["start"], now if item["end"] is None else min(item["end"], now))
              for item in intervals if item["start"] < now]
    if not pauses:
        return segments
    boundaries = sorted({t for start, end in pauses for t in (start, end)})
    result = []
    from bisect import bisect_right, bisect_left
    pause_index = 0
    for segment in segments:
        begin, end = segment[:2]
        points = [begin, *boundaries[bisect_right(boundaries, begin):bisect_left(boundaries, end)], end]
        for a, b in zip(points, points[1:]):
            while pause_index < len(pauses) and pauses[pause_index][1] <= a:
                pause_index += 1
            if pause_index < len(pauses) and pauses[pause_index][0] <= a < pauses[pause_index][1]:
                # This is an effective work status, not a VPN observation:
                # retain known coverage/income without counting the time as work.
                # A sleep estimate is inferred work, not an observation; a
                # manual pause must not manufacture observed coverage from it.
                effective = segment[2]
                if effective == "connected":
                    effective = "unknown" if len(segment) > 3 and segment[3] == "sleep_estimate" else "paused"
                current = (effective, "manual_paused")
            else:
                current = (segment[2], segment[3] if len(segment) > 3 else "vpn")
            if result and result[-1][1] == a and result[-1][2:] == current:
                result[-1] = (result[-1][0], b, *current)
            else:
                result.append((a, b, *current))
    return result


def _overlay_manual(segments, manual):
    """Manual work intervals override statuses, preserving the original list."""
    intervals = _merge_intervals([pair for entry in manual.values()
                                  for pair in (entry.get("_intervals", []) if entry["kind"] == "intervals"
                                               else entry.get("_tail_intervals", []))])
    overrides = sorted((entry["_override"], entry["_intervals"]) for entry in manual.values() if "_override" in entry)
    if not intervals and not overrides:
        return segments
    points = sorted({point for begin, finish, *_ in segments for point in (begin, finish)}
                    | {point for begin, finish in intervals for point in (begin, finish)}
                    | {point for span, ranges in overrides for begin, finish in [span, *ranges] for point in (begin, finish)})
    result, raw_index, manual_index, override_index = [], 0, 0, 0
    for begin, finish in zip(points, points[1:]):
        while raw_index < len(segments) and segments[raw_index][1] <= begin:
            raw_index += 1
        while manual_index < len(intervals) and intervals[manual_index][1] <= begin:
            manual_index += 1
        while override_index < len(overrides) and overrides[override_index][0][1] <= begin:
            override_index += 1
        if override_index < len(overrides) and overrides[override_index][0][0] <= begin:
            state = "connected" if any(a <= begin < b for a, b in overrides[override_index][1]) else "disconnected"
            source = "manual_override"
        elif manual_index < len(intervals) and intervals[manual_index][0] <= begin:
            state, source = "connected", "manual"
        elif raw_index < len(segments) and segments[raw_index][0] <= begin:
            state = segments[raw_index][2]
            source = segments[raw_index][3] if len(segments[raw_index]) > 3 else "vpn"
        else:
            state, source = "unknown", "vpn"
        if result and result[-1][1] == begin and result[-1][2:] == (state, source):
            result[-1] = (result[-1][0], finish, state, source)
        else:
            result.append((begin, finish, state, source))
    return result


def _manual_in_window(manual, start, end, config):
    active = {}
    for day, entry in manual.items():
        if entry["kind"] == "daily_total":
            applies = (_midnight(day, config["zone"]) < end
                       and _midnight(day + timedelta(days=1), config["zone"]) > start)
        elif entry["kind"] == "intervals_override":
            applies = _overlap(*entry["_override"], start, end) > 0 or any(
                _overlap(begin, finish, start, end) > 0 for begin, finish in entry.get("_tail_intervals", []))
        else:
            applies = any(_overlap(begin, finish, start, end) > 0
                          for begin, finish in entry["_intervals"])
        if applies:
            active[day] = entry
    return active


def _apply_estimates(known, manual):
    for day, entry in manual.items():
        if entry["kind"] == "daily_total":
            data = known.setdefault(day, {"work": 0.0, "observed": 0.0, "scheduled_observed": 0.0})
            data["work"] = entry["hours"] * 3600
            data["sleep_estimated"] = 0.0
            # This flag establishes a recorded date without inventing observed
            # seconds, timestamps, VPN connectivity, or schedule coverage.
            data["manual_recorded"] = True


def _recorded(entry):
    return entry["observed"] > 0 or entry.get("manual_recorded", False) or entry.get("sleep_estimated", 0) > 0


def _percentage(part: float, whole: float) -> float | None:
    return min(100.0, max(0.0, 100.0 * part / whole)) if whole > 0 else None


def _day_summary(day, entry, manual_entry, vpn_entry, begin, end, config, annual_days,
                 *, future=False, partial_day=False):
    """Share one daily representation between the heatmap and period chart."""
    elapsed = max(0.0, end - begin)
    slot = _schedule(day, config)
    expected = _overlap(begin, end, *slot) if slot is not None and not future else 0.0
    if future:
        status = "future"
    elif not _recorded(entry):
        status = "unknown"
    elif entry.get("manual_recorded") or partial_day:
        status = "partial"
    elif entry["observed"] >= elapsed - 1e-6:
        status = "observed"
    else:
        status = "partial"
    income = _daily_income(day, _recorded(entry), config, annual_days)
    rate_status, actual_rate = _actual_rate(income, entry["work"], minimum_hour=True)
    if not _recorded(entry):
        rate_status = "no_records"
    return {
        "date": day.isoformat(),
        "work_hours": entry["work"] / 3600,
        "observed_hours": entry["observed"] / 3600,
        "scheduled_hours": expected / 3600,
        "coverage_percent": _percentage(entry["scheduled_observed"], expected),
        "status": status,
        "income": income,
        "actual_rate": actual_rate,
        "rate_status": rate_status,
        "rate_floor_applied": _rate_floor_applied(income, entry["work"]),
        "manual_kind": manual_entry["kind"] if manual_entry else None,
        "source": (("manual_estimate" if manual_entry["kind"] == "daily_total" else "manual")
                   if manual_entry else ("sleep_estimate" if entry.get("sleep_estimated", 0) else "vpn")),
        "sleep_estimated_hours": entry.get("sleep_estimated", 0.0) / 3600,
        "vpn_work_hours": vpn_entry.get("work", 0.0) / 3600,
        "manual_note": manual_entry.get("note", "") if manual_entry else "",
    }


def _timeline(segments: list, start: float, end: float, zone: ZoneInfo, limit=500) -> list:
    clipped = []

    def append(begin, finish, state, source="vpn"):
        if finish <= begin:
            return
        if clipped and clipped[-1][2:] == (state, source) and clipped[-1][1] == begin:
            clipped[-1] = (clipped[-1][0], finish, state, source)
        else:
            clipped.append((begin, finish, state, source))

    cursor = start
    for segment in segments:
        begin, finish, state = segment[:3]
        source = segment[3] if len(segment) > 3 else "vpn"
        if finish <= start:
            continue
        if begin >= end:
            break
        begin, finish = max(begin, start), min(finish, end)
        append(cursor, begin, "unknown")
        append(begin, finish, state, source)
        cursor = finish
    append(cursor, end, "unknown")
    return [
        {
            "start": datetime.fromtimestamp(begin, zone).isoformat(),
            "end": datetime.fromtimestamp(finish, zone).isoformat(),
            "state": state,
            "source": source,
        }
        for begin, finish, state, source in (clipped[-limit:] if limit else clipped)
    ]


def history_day(samples, settings, day, now, manual_entries=None, sleep_intervals=None, pending_count=0, edit_limit=None):
    """Return precise source segments and a clearly rounded optional editing draft."""
    config = _configuration(settings)
    zone = config["zone"]
    start, finish = _midnight(day, zone), min(_midnight(day + timedelta(days=1), zone), now)
    raw = _segments(samples, now)
    manual = _manual_records(manual_entries, now, config)
    entry = manual.get(day)
    slept = _overlay_sleep(raw, sleep_intervals, now, config["pause_on_sleep"])
    effective = _overlay_manual(_overlay_manual_pauses(_overlay_night(slept, config), settings.get("manual_pauses", []), now), manual)
    details = _timeline(effective, start, finish, zone, limit=None)
    raw_details = _timeline(raw, start, finish, zone, limit=None)
    edit_cutoff = None
    if day == datetime.fromtimestamp(now, zone).date():
        published = [float(s['ts']) for s in samples if isinstance(s, dict) and type(s.get('ts')) in (int, float)
                     and math.isfinite(s['ts']) and start <= s['ts'] <= now]
        latest = max(published) if published else (start if pending_count else now)
        edit_cutoff = int(min(now, latest) // 60) * 60
        if edit_limit is not None:
            edit_cutoff = min(edit_cutoff, edit_limit)
    editable_details = _timeline(effective, start, min(finish, edit_cutoff), zone, limit=None) if edit_cutoff is not None else details
    editable, reason = [], None
    offset_changes = datetime.fromtimestamp(start, zone).utcoffset() != datetime.fromtimestamp(_midnight(day + timedelta(days=1), zone), zone).utcoffset()
    # Calculation merges contiguous work, but the editor needs the explicitly
    # saved boundaries back. Only reinsert boundaries into effective connected
    # spans, so later VPN samples and pauses after today's cutoff stay intact.
    boundaries = []
    if entry and entry["kind"] in ("intervals", "intervals_override") and not offset_changes:
        saved = entry["intervals"]
        starts = {part["start"] for part in saved}
        boundaries = sorted({int(part["end"][:2]) * 60 + int(part["end"][3:])
                             for part in saved if part["end"] in starts})
        if boundaries:
            cut_times = [datetime.combine(day, datetime.min.time(), zone) + timedelta(minutes=value)
                         for value in boundaries]
            split_details = []
            for part in details:
                a, b = datetime.fromisoformat(part["start"]), datetime.fromisoformat(part["end"])
                cuts = [cut for cut in cut_times if part["state"] == "connected" and a < cut < b]
                points = [a, *cuts, b]
                split_details.extend({**part, "start": x.isoformat(), "end": y.isoformat()}
                                     for x, y in zip(points, points[1:]))
            details = split_details
    if entry and entry["kind"] == "daily_total":
        editable, reason = None, "当天只有总时长估算，不能推测具体时段。"
    elif offset_changes:
        editable, reason = None, "当天发生时区偏移变化，无法安全地自动转换成分钟时段。" + ("今天请使用补充时段。" if edit_cutoff is not None else "")
    else:
        spans = []
        for part in editable_details:
            if part["state"] != "connected":
                continue
            a, b = datetime.fromisoformat(part["start"]), datetime.fromisoformat(part["end"])
            a_minutes = min(1440, (a.hour * 3600 + a.minute * 60 + a.second + 30) // 60)
            b_minutes = 1440 if b.date() > day else min(1440, (b.hour * 3600 + b.minute * 60 + b.second + 30) // 60)
            if b_minutes > a_minutes:
                spans.append((a_minutes, b_minutes))
        spans = _merge_intervals(spans)
        if boundaries:
            spans = [(x, y) for a, b in spans
                     for x, y in zip([a, *(cut for cut in boundaries if a < cut < b)],
                                     [*(cut for cut in boundaries if a < cut < b), b])]
        if len(spans) > 12:
            editable, reason = None, "当天超过 12 个时段，无法自动填入，请手动选择需要保留的时段。"
        else:
            editable = [{"start": f"{int(a)//60:02d}:{int(a)%60:02d}", "end": f"{int(b)//60:02d}:{int(b)%60:02d}"} for a, b in spans]
    # Supplemental work saved after the current correction snapshot remains
    # distinct from the editable range. Expose it so the editor never hides a
    # saved tail or treats its intervening unknown gaps as confirmed work.
    protected_tail_intervals = []
    if edit_cutoff is not None and entry and entry["kind"] == "intervals_override":
        now_minute = int(now // 60) * 60
        for a, b in entry.get("_tail_intervals", []):
            a, b = max(a, edit_cutoff), min(b, now_minute)
            if a >= b:
                continue
            local_a, local_b = datetime.fromtimestamp(a, zone), datetime.fromtimestamp(b, zone)
            protected_tail_intervals.append({"start": local_a.strftime("%H:%M"), "end": local_b.strftime("%H:%M")})
    return {"date": day.isoformat(), "timezone": str(zone), "segments": details, "raw_segments": raw_details,
            "manual_entry": {k: v for k, v in entry.items() if not k.startswith('_')} if entry else None,
            "editable_intervals": editable, "editable_reason": reason, "edit_cutoff": edit_cutoff,
            "protected_tail_intervals": protected_tail_intervals,
            "today_override_available": not (edit_cutoff is not None and offset_changes)}


def calendar_month(samples, settings, first, now=None, manual_entries=None, sleep_intervals=None):
    """Daily heatmap values for an arbitrary local calendar month."""
    now = time.time() if now is None else float(now)
    config = _configuration(settings)
    zone = config["zone"]
    local_today = datetime.fromtimestamp(now, zone).date()
    last = _shift_months(first, 1)
    start = _midnight(first, zone)
    raw = _segments(samples, now)
    manual = _manual_records(manual_entries, now, config)
    slept = _overlay_sleep(raw, sleep_intervals, now, config["pause_on_sleep"])
    segments = _overlay_manual(_overlay_manual_pauses(_overlay_night(slept, config), settings.get("manual_pauses", []), now), manual)
    known = _known_by_day(segments, start, now, config)
    vpn = _known_by_day(raw, start, now, config)
    active = _manual_in_window(manual, start, now, config)
    _apply_estimates(known, active)
    annual_days = {}
    empty = {"work": 0.0, "observed": 0.0, "scheduled_observed": 0.0}
    return [_day_summary(day, known.get(day, empty), active.get(day), vpn.get(day, {}),
                         _midnight(day, zone), min(_midnight(day + timedelta(days=1), zone), now),
                         config, annual_days, future=day > local_today)
            for day in _dates(first, last)]


def summarize(samples, settings, period="week", now=None, manual_entries=None, sleep_intervals=None) -> dict:
    """Return period metrics/days, yearly/recent heatmaps, and a recent timeline.

    Each configured workday with a positive known observation interval earns
    one fixed daily salary, even when observations occur outside schedule hours.
    Entirely unknown dates earn nothing; non-workdays only add VPN work hours.
    Salary changes take effect on local calendar dates. Theoretical daily hours
    define only the hourly-rate baseline and never filter observed work or pay.
    Manual totals override a past date's work without inventing time intervals;
    manual intervals are united with VPN work and clipped to the present.
    ``coverage_percent`` retains the legacy schedule-overlap diagnostic; day
    ``status`` additionally preserves missing observations outside the schedule.
    """
    now = time.time() if now is None else float(now)
    if not math.isfinite(now):
        raise ValueError("当前时间必须是有限时间戳")
    if period == "halfyear":
        period = "half"
    config = _configuration(settings)
    zone = config["zone"]
    local_now = datetime.fromtimestamp(now, zone)
    year = local_now.year
    start = _period_start(period, now, zone)
    raw_segments = _segments(samples, now)
    manual = _manual_records(manual_entries, now, config)
    sleep_segments = _overlay_sleep(raw_segments, sleep_intervals, now, config["pause_on_sleep"])
    segments = _overlay_manual(_overlay_manual_pauses(_overlay_night(sleep_segments, config), settings.get("manual_pauses", []), now), manual)
    annual_days = {year: _annual_workdays(year, config)}
    salary = _salary_on(local_now.date(), config)
    theoretical_rate = (salary / (annual_days[year] * config["theoretical_daily_hours"])
                        if salary is not None else None)

    known = _known_by_day(segments, start, now, config)
    active_manual = _manual_in_window(manual, start, now, config)
    _apply_estimates(known, active_manual)
    work = sum(day["work"] for day in known.values())
    observed = sum(day["observed"] for day in known.values())
    observed_scheduled = sum(day["scheduled_observed"] for day in known.values())
    scheduled = _scheduled_seconds(start, now, config)
    recorded_days = sum(_recorded(data) for data in known.values())
    daily_incomes = [_daily_income(day, _recorded(data), config, annual_days)
                    for day, data in known.items()]
    salary_incomplete = any(value is None for value in daily_incomes)
    # A missing salary is not zero pay. Preserve the unset-salary empty state,
    # while an observed non-workday legitimately contributes no extra income.
    income = (None if salary_incomplete or (not daily_incomes and salary is None)
              else sum(daily_incomes))
    rate_status, actual_rate = _actual_rate(income, work, minimum_hour=period == "today")
    delta = (
        (actual_rate / theoretical_rate - 1) * 100
        if actual_rate is not None and theoretical_rate is not None
        else None
    )

    # Use the same clipped per-date totals as the headline metrics. The current
    # year heatmap cannot supply the previous-year portion of rolling windows.
    empty_day = {"work": 0.0, "observed": 0.0, "scheduled_observed": 0.0}
    period_vpn = _known_by_day(raw_segments, start, now, config)
    period_days = []
    first_day = datetime.fromtimestamp(start, zone).date()
    for day in _dates(first_day, local_now.date() + timedelta(days=1)):
        midnight = _midnight(day, zone)
        next_midnight = _midnight(day + timedelta(days=1), zone)
        begin, end = max(midnight, start), min(next_midnight, now)
        partial_day = begin > midnight or end < next_midnight
        daily = _day_summary(day, known.get(day, empty_day), active_manual.get(day),
                             period_vpn.get(day, {}), begin, end, config, annual_days,
                             partial_day=partial_day)
        daily["partial_day"] = partial_day
        period_days.append(daily)

    year_start = _midnight(date(year, 1, 1), zone)
    year_known = _known_by_day(segments, year_start, now, config)
    year_vpn = _known_by_day(raw_segments, year_start, now, config)
    year_manual = _manual_in_window(manual, year_start, now, config)
    _apply_estimates(year_known, year_manual)
    heatmap = []
    for day in _dates(date(year, 1, 1), date(year + 1, 1, 1)):
        begin = _midnight(day, zone)
        end = min(_midnight(day + timedelta(days=1), zone), now)
        heatmap.append(_day_summary(day, year_known.get(day, empty_day), year_manual.get(day),
                                   year_vpn.get(day, {}), begin, end, config, annual_days,
                                   future=day > local_now.date()))

    # The focused heatmap is independent of the selected statistics period and
    # crosses New Year. Build from observations, not a slice of this year's map.
    recent_first = _shift_months(local_now.date(), -3)
    recent_last = _shift_months(local_now.date(), 3)
    recent_start = _midnight(recent_first, zone)
    recent_known = _known_by_day(segments, recent_start, now, config)
    recent_vpn = _known_by_day(raw_segments, recent_start, now, config)
    recent_manual = _manual_in_window(manual, recent_start, now, config)
    _apply_estimates(recent_known, recent_manual)
    heatmap_recent = []
    for day in _dates(recent_first, recent_last + timedelta(days=1)):
        begin = _midnight(day, zone)
        end = min(_midnight(day + timedelta(days=1), zone), now)
        heatmap_recent.append(_day_summary(day, recent_known.get(day, empty_day), recent_manual.get(day),
                                          recent_vpn.get(day, {}), begin, end, config, annual_days,
                                          future=day > local_now.date()))

    return {
        "period": period,
        "label": PERIOD_LABELS[period],
        "start": datetime.fromtimestamp(start, zone).isoformat(),
        "end": local_now.isoformat(),
        "theoretical_rate": theoretical_rate,
        "theoretical_daily_hours": config["theoretical_daily_hours"],
        "current_annual_salary": salary,
        "salary_incomplete": salary_incomplete,
        "rate_status": rate_status,
        "actual_rate": actual_rate,
        "rate_floor_applied": period == "today" and _rate_floor_applied(income, work),
        "income": income,
        "recorded_days": recorded_days,
        "manual_days": len(active_manual),
        "pause_on_sleep": config["pause_on_sleep"],
        "sleep_estimated_hours": sum(entry.get("sleep_estimated", 0.0) for entry in known.values()) / 3600,
        "estimated_hours": sum(entry["hours"] for entry in active_manual.values() if entry["kind"] == "daily_total"),
        "manual_entries": [{key: value for key, value in entry.items() if not key.startswith("_")}
                           for _, entry in sorted(active_manual.items())],
        "work_hours": work / 3600,
        "observed_hours": observed / 3600,
        "scheduled_hours": scheduled / 3600,
        "observed_scheduled_hours": observed_scheduled / 3600,
        "coverage_percent": _percentage(observed_scheduled, scheduled),
        "delta_percent": delta,
        "period_comparison": _period_comparison(period, now, config, segments, manual, actual_rate),
        "days": heatmap,
        "heatmap_recent_days": heatmap_recent,
        "heatmap_window": {"start": recent_first.isoformat(), "end": recent_last.isoformat()},
        "period_days": period_days,
        "timeline": _timeline(segments, start, now, zone),
    }
