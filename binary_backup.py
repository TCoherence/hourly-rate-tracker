"""Consistent SQLite snapshots with bounded-memory, validated local restore."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile

from exporting import json_backup, validate_backup

# Large enough for decades of normal sampling; prevents a malformed upload
# from filling the disk without an explicit future format change.
MAX_SQLITE_BYTES = 2 * 1024 * 1024 * 1024


def snapshot_file(store, prefix="hourly-rate-snapshot-"):
    """Use the SQLite online backup API; callers hold the application lock."""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".sqlite3", dir=store.path)
    os.close(fd)
    try:
        with store.lock:
            dest = sqlite3.connect(name)
            try:
                store.db.backup(dest)
            finally:
                dest.close()
        if os.path.getsize(name) > MAX_SQLITE_BYTES:
            raise ValueError("本机数据超过 SQLite 备份上限（2 GiB）。")
        return Path(name)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def _schema(connection):
    # Compare internal objects too: an untrusted database can forge reserved
    # names by editing sqlite_master with writable_schema.
    return connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")


def validate_sqlite_backup(source, store, now):
    """Reject altered schemas and invalid records before touching the real DB.

    Check observations as a stream rather than building a multi-million-row
    JSON object. Reuse the regular JSON validation for compact metadata, manual
    entries and sleep intervals. A foreign schema, triggers or views cannot be
    copied into the live database.
    """
    # Bound individual SQLite rows/strings even when an untrusted backup claims
    # a multi-gigabyte text field. Normal application settings and notes are
    # many orders of magnitude smaller, while observations are streamed.
    # Python 3.10 lacks setlimit; the upload still has the overall 2 GiB cap.
    if hasattr(source, "setlimit"):
        source.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 8 * 1024 * 1024)
    source.execute("PRAGMA trusted_schema=OFF")
    # Stream the comparison as a malicious schema can contain many objects.
    count_query = "SELECT count(*) FROM sqlite_master"
    if source.execute(count_query).fetchone() != store.db.execute(count_query).fetchone():
        raise ValueError("SQLite 备份结构与当前版本不兼容。")
    expected = _schema(store.db)
    actual = _schema(source)
    while True:
        left, right = actual.fetchone(), expected.fetchone()
        if left != right:
            raise ValueError("SQLite 备份结构与当前版本不兼容。")
        if left is None:
            break
    if source.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise ValueError("SQLite 备份完整性检查失败。")
    # Verification entries are intentionally not imported, so do not retain
    # their values in memory. Reject other unknown metadata keys.
    for (key,) in source.execute("SELECT key FROM meta"):
        if not isinstance(key, str) or (key not in ("settings", "published_seq", "last_synced_at") and not key.startswith("verification:")):
            raise ValueError("SQLite 备份包含不支持的元数据。")
    meta = {key: json.loads(value) for key, value in source.execute(
        "SELECT key,value FROM meta WHERE key IN ('settings','published_seq','last_synced_at')")}
    settings = meta.pop("settings", {})
    published = meta.get("published_seq", 0)
    max_id = 0
    for ident, stamp, state in source.execute("SELECT id,ts,state FROM observations ORDER BY id"):
        # Reject IDs near SQLite's signed-64-bit exhaustion rather than let a
        # crafted file make the restored collector fail almost immediately.
        if type(ident) is not int or ident <= max_id or ident >= 2**62 or type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 or state not in ("connected", "disconnected", "unknown"):
            raise ValueError("SQLite 备份包含无效的采样数据。")
        try:
            datetime.fromtimestamp(stamp, timezone.utc)
        except (ValueError, OSError, OverflowError):
            raise ValueError("SQLite 备份包含无效的采样时间。") from None
        max_id = ident
    if type(published) is not int or not 0 <= published <= max_id:
        raise ValueError("SQLite 备份的同步水位无效。")

    # Reuse the JSON validator with one manual record at a time. Dates are
    # unique because they are SQLite primary keys; backup cross-references are
    # checked by a indexed lookup, without loading all days in memory.
    base = json_backup({"settings": settings, "observations": [], "sleep_intervals": [],
        "manual_entries": [], "manual_override_backups": [],
        "metadata": {"published_seq": 0, "last_synced_at": meta.get("last_synced_at")}}, now)
    safe = validate_backup(base, directory=store.path)
    for key, payload in source.execute("SELECT date,payload FROM manual_entries ORDER BY date"):
        entry = json.loads(payload)
        if not isinstance(entry, dict) or entry.get("date") != key:
            raise ValueError("SQLite 备份的手动记录日期不一致。")
        validate_backup({**base, "manual_entries": [entry]}, directory=store.path)
    for key, payload in source.execute("SELECT date,payload FROM manual_override_backups ORDER BY date"):
        entry = json.loads(payload)
        original = source.execute("SELECT payload FROM manual_entries WHERE date=?", (key,)).fetchone()
        if not isinstance(entry, dict) or entry.get("date") != key or not original:
            raise ValueError("SQLite 备份的手动记录日期不一致。")
        main = json.loads(original[0])
        validate_backup({**base, "manual_entries": [main], "manual_override_backups": [entry]}, directory=store.path)

    def timestamp(value, optional=False):
        if value is None and optional:
            return
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("SQLite 备份包含无效的睡眠时间。")
        try:
            datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OSError, OverflowError):
            raise ValueError("SQLite 备份包含无效的睡眠时间。") from None

    previous_end, open_sleep = None, False
    for start, end, state, checked, abandoned in source.execute(
            "SELECT start,end,state,last_sample_ts,abandoned FROM sleep_intervals ORDER BY start"):
        if type(abandoned) is not int or abandoned not in (0, 1) or state not in ("connected", "disconnected", "unknown"):
            raise ValueError("SQLite 备份包含无效的睡眠状态。")
        timestamp(start); timestamp(end, True); timestamp(checked, True)
        if end is not None and end < start:
            raise ValueError("SQLite 备份包含无效的睡眠区间。")
        if not abandoned:
            if open_sleep or (previous_end is not None and start < previous_end):
                raise ValueError("SQLite 备份包含重叠的睡眠区间。")
            open_sleep = end is None
            previous_end = end
    safe["metadata"]["published_seq"] = published
    safe["max_observation_id"] = max_id
    return safe


def restore_sqlite_file(app, uploaded):
    """Restore under the collector lock; first persist an online rollback copy."""
    # uploaded is an app-owned temporary file, never a user-supplied path.
    if uploaded.stat().st_size > MAX_SQLITE_BYTES:
        raise ValueError("SQLite 备份超过 2 GiB。")
    source = sqlite3.connect(str(uploaded))
    try:
        with app.lock, app.store.lock:
            safe = validate_sqlite_backup(source, app.store, __import__('time').time())
            rollback = snapshot_file(app.store, "before-restore-")
            # Sanitize this private copy before it becomes the live database.
            with source:
                source.execute("DELETE FROM meta")
                source.executemany("INSERT INTO meta(key,value) VALUES(?,?)", [
                    ("settings", json.dumps(safe["settings"], ensure_ascii=False, allow_nan=False)),
                    ("published_seq", json.dumps(safe["metadata"]["published_seq"])),
                    ("last_synced_at", json.dumps(safe["metadata"]["last_synced_at"]))])
                source.execute("UPDATE sleep_intervals SET abandoned=1 WHERE end IS NULL")
                # sqlite_sequence is internal and excluded from schema checks.
                # Never trust a crafted sequence value from an uploaded backup.
                source.execute("DELETE FROM sqlite_sequence")
                source.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('observations',?)", (safe["max_observation_id"],))
            source.backup(app.store.db)
            app.reset_screen_tracker()
            app.state, app.message, app.last_checked = "disabled", "数据已恢复，采集已暂停", None
            app._collector_provider = safe["settings"]["provider"]
            app.collector_wake.set()
            with app.cache_lock:
                app.cache.clear()
            return {"ok": True, "rollback_path": str(rollback), "tracking_enabled": False}
    finally:
        source.close()
