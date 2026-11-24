"""Legacy compatibility using only fictional providers and temporary data."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import Application
from autostart import LABEL, LoginItem
from binary_backup import restore_sqlite_file, snapshot_file
from exporting import json_backup
import vpn


OLD_SCRIPT = "fictional_old_cli"
OLD_SYSTEM = "fictional_old_native"
OLD_ENV = "HOURLY_RATE_FICTIONAL_CLI"
NEW_ENV = "HOURLY_RATE_ADAPTER_LEGACY_PATH"


def install_compat(directory):
    path = Path(directory) / "adapters" / "legacy-compat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1,
        "providers": {
            OLD_SCRIPT: {"provider": "script", "status_script_path": "local_adapter"},
            OLD_SYSTEM: {"provider": "verified_system"},
        },
        "environment": {OLD_ENV: NEW_ENV},
    }))
    path.chmod(0o600)
    return path


class FakeLaunchctl:
    def __call__(self, argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout='{"' + LABEL + '" => enabled}', stderr="")


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source_dir, self.target_dir = self.root / "source", self.root / "target"
        self.source_dir.mkdir(); self.target_dir.mkdir()
        install_compat(self.source_dir); install_compat(self.target_dir)
        self.source = Application(self.source_dir, detector=lambda _: ("unknown", "test"))
        self.target = Application(self.target_dir, detector=lambda _: ("unknown", "test"))
        self.addCleanup(self.source.close)
        self.addCleanup(self.target.close)
        self.now = datetime.now(timezone.utc).timestamp()
        day = (datetime.now(timezone.utc) - timedelta(days=2)).date()
        self.day = day.isoformat()
        start = datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc).timestamp()
        self.source.store.save_settings({
            "timezone": "UTC", "annual_salary": 95000, "provider": "script",
            "status_script_path": str(self.source_dir / "adapters" / "status"),
            "tracking_enabled": True,
        })
        self.source.store.record(start, "connected")
        self.source.store.record(start + 30, "connected")
        self.source.store.sync(start + 45)
        self.source.store.record(start + 60, "disconnected")  # pending sample
        self.source.store.save_manual_entries([{
            "date": self.day, "kind": "intervals", "note": "fictional",
            "intervals": [{"start": "10:00", "end": "11:00"}],
        }], now=self.now)
        self.source.store.save_manual_entries([{
            "date": self.day, "kind": "intervals_override", "note": "fictional correction",
            "intervals": [{"start": "09:00", "end": "10:00"},
                          {"start": "10:00", "end": "11:30"}],
        }], now=self.now)
        with self.source.store.db:
            self.source.store.db.execute(
                "INSERT INTO sleep_intervals(start,end,state,last_sample_ts,abandoned) VALUES(?,?,?,?,?)",
                (start + 80, start + 120, "connected", start + 75, 0))
        self.snapshot = self.source.store.export_snapshot()
        self.target.store.save_settings({"timezone": "UTC", "annual_salary": 57000})
        self.target.store.record(start - 500, "unknown")
        self.target.store.sync(self.now)

    def legacy_settings(self):
        settings = copy.deepcopy(self.snapshot["settings"])
        settings["provider"] = OLD_SCRIPT
        settings.pop("status_script_path", None)
        return settings

    def assert_imported_records(self, snapshot):
        for key in ("observations", "manual_entries", "manual_override_backups", "sleep_intervals"):
            self.assertEqual(snapshot[key], self.snapshot[key], key)
        self.assertEqual(snapshot["metadata"]["published_seq"], self.snapshot["metadata"]["published_seq"])
        self.assertEqual(snapshot["metadata"]["last_synced_at"], self.snapshot["metadata"]["last_synced_at"])
        self.assertEqual(snapshot["settings"]["annual_salary"], 95000)
        self.assertEqual(snapshot["settings"]["provider"], "script")
        self.assertEqual(snapshot["settings"]["status_script_path"], str(self.target_dir / "adapters" / "status"))
        self.assertFalse(snapshot["settings"]["tracking_enabled"])
        with patch("app.time.time", return_value=self.now):
            source_day = self.source.history_day(self.day)
            target_day = self.target.history_day(self.day)
        for key in ("segments", "raw_segments", "manual_entry", "editable_intervals"):
            self.assertEqual(target_day[key], source_day[key], key)

    def test_existing_database_migrates_in_memory_and_keeps_history(self):
        legacy = self.legacy_settings()
        with self.source.store.db:
            self.source.store._set("settings", legacy)
        settings = self.source.store.settings()
        self.assertEqual(settings["provider"], "script")
        self.assertTrue(settings["tracking_enabled"])
        self.assertEqual(settings["status_script_path"], str(self.source_dir / "adapters" / "status"))
        self.assertEqual(self.source.store._get("settings")["provider"], OLD_SCRIPT)
        after = self.source.store.export_snapshot()
        for key in ("observations", "manual_entries", "manual_override_backups", "sleep_intervals", "metadata"):
            self.assertEqual(after[key], self.snapshot[key], key)
        self.source.store.save_settings({"annual_salary": 96000})
        after_save = self.source.store.export_snapshot()
        for key in ("observations", "manual_entries", "manual_override_backups", "sleep_intervals", "metadata"):
            self.assertEqual(after_save[key], self.snapshot[key], key)
        self.assertEqual(after_save["settings"]["annual_salary"], 96000)

    def test_old_system_backup_preserves_verification_requirement(self):
        payload = json_backup(copy.deepcopy(self.snapshot), self.now)
        payload["settings"]["provider"] = OLD_SYSTEM
        service = "12345678-1234-1234-1234-123456789abc"
        payload["settings"]["service_id"] = service
        self.target.store.verify_state(service, "connected")
        self.target.store.verify_state(service, "disconnected")
        with patch("app.time.time", return_value=self.now):
            outcome = self.target.restore_backup(payload)
        self.assertFalse(outcome["tracking_enabled"])
        self.assertEqual(self.target.store.settings()["provider"], "verified_system")
        self.assertFalse(self.target.store.verification(service)["verified"])
        with self.assertRaises(ValueError):
            self.target.settings({"tracking_enabled": True})
        for key in ("observations", "manual_entries", "manual_override_backups", "sleep_intervals"):
            self.assertEqual(self.target.store.export_snapshot()[key], self.snapshot[key], key)

    def test_json_restore_keeps_original_and_creates_rollback(self):
        payload = json_backup(copy.deepcopy(self.snapshot), self.now)
        payload["settings"] = self.legacy_settings()
        original = self.root / "fictional-backup.json"
        original.write_text(json.dumps(payload, ensure_ascii=False))
        before_bytes = original.read_bytes()
        before = self.target.store.export_snapshot()
        with patch("app.time.time", return_value=self.now):
            outcome = self.target.restore_backup(json.loads(original.read_text()))
        self.assertEqual(original.read_bytes(), before_bytes)
        self.assertFalse(outcome["tracking_enabled"])
        rollback = Path(outcome["rollback_path"])
        self.assertEqual(rollback.stat().st_mode & 0o777, 0o600)
        old = json.loads(rollback.read_text())
        self.assertEqual(old["observations"], before["observations"])
        self.assertEqual(old["settings"], before["settings"])
        self.assert_imported_records(self.target.store.export_snapshot())

    def test_sqlite_restore_keeps_original_and_creates_rollback(self):
        original = snapshot_file(self.source.store)
        with sqlite3.connect(original) as connection:
            connection.execute("UPDATE meta SET value=? WHERE key='settings'", (json.dumps(self.legacy_settings()),))
        before_bytes = original.read_bytes()
        upload = self.target_dir / "simulated-upload.sqlite3"
        shutil.copyfile(original, upload)
        before = self.target.store.export_snapshot()
        outcome = restore_sqlite_file(self.target, upload)
        self.assertEqual(original.read_bytes(), before_bytes)
        self.assertFalse(outcome["tracking_enabled"])
        rollback = Path(outcome["rollback_path"])
        self.assertEqual(rollback.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(f"file:{rollback}?mode=ro", uri=True) as connection:
            settings = json.loads(connection.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0])
            observations = connection.execute("SELECT id,ts,state FROM observations ORDER BY id").fetchall()
        self.assertEqual(settings, before["settings"])
        self.assertEqual(observations, [(row["id"], row["ts"], row["state"]) for row in before["observations"]])
        self.assert_imported_records(self.target.store.export_snapshot())

    def test_missing_private_map_does_not_modify_records_or_backup(self):
        payload = json_backup(copy.deepcopy(self.snapshot), self.now)
        payload["settings"] = self.legacy_settings()
        (self.target_dir / "adapters" / "legacy-compat.json").unlink()
        original = copy.deepcopy(payload)
        before = self.target.store.export_snapshot()
        with self.assertRaises(ValueError):
            self.target.restore_backup(payload)
        self.assertEqual(payload, original)
        self.assertEqual(self.target.store.export_snapshot(), before)
        self.assertFalse(list(self.target_dir.glob("before-restore-*")))

    def test_old_environment_reaches_login_item_and_script(self):
        executable = self.target_dir / "adapters" / "status"
        executable.write_text('#!' + sys.executable + '\nimport os\nprint("connected" if os.environ.get("' + NEW_ENV + '") == "/opt/example/cli" else "unknown")\n')
        executable.chmod(0o700)
        project = self.root / "project"
        project.mkdir(); (project / "app.py").write_text("")
        item = LoginItem(self.target_dir, 8765, home=self.root, root=project, executable=sys.executable,
                         platform="darwin", environment={OLD_ENV: "/opt/example/cli"}, runner=FakeLaunchctl(), uid=os.getuid())
        item.set_enabled(True)
        with item.path.open("rb") as stream:
            job = plistlib.load(stream)
        env = job["EnvironmentVariables"]
        with patch.dict(os.environ, env, clear=True), patch.object(vpn.sys, "platform", "darwin"):
            state, _ = vpn.detect({"provider": "script", "status_script_path": str(executable), "tracking_enabled": True})
        self.assertEqual(state, "connected")
        # A previously installed login item can still carry the old name.
        with patch.dict(os.environ, {OLD_ENV: "/opt/example/cli"}, clear=True), patch.object(vpn.sys, "platform", "darwin"):
            state, _ = vpn.detect({"provider": "script", "status_script_path": str(executable), "tracking_enabled": True}, compatibility_dir=self.target_dir)
        self.assertEqual(state, "connected")

    def test_malformed_mapping_does_not_guess_script_status(self):
        executable = self.target_dir / "adapters" / "status"
        executable.write_text('#!' + sys.executable + '\nimport os\nprint("connected" if os.environ.get("' + NEW_ENV + '") == "/opt/example/cli" else "disconnected")\n')
        executable.chmod(0o700)
        config = self.target_dir / "adapters" / "legacy-compat.json"
        config.write_text("not valid JSON")
        settings = {"provider": "script", "status_script_path": str(executable), "tracking_enabled": True}
        with patch.dict(os.environ, {OLD_ENV: "/opt/example/cli"}, clear=True), patch.object(vpn.sys, "platform", "darwin"):
            state, _ = vpn.detect(settings, compatibility_dir=self.target_dir)
        self.assertEqual(state, "unknown")
        # An explicit generic path is sufficient and takes precedence.
        with patch.dict(os.environ, {OLD_ENV: "/opt/different/cli", NEW_ENV: "/opt/example/cli"}, clear=True), patch.object(vpn.sys, "platform", "darwin"):
            state, _ = vpn.detect(settings, compatibility_dir=self.target_dir)
        self.assertEqual(state, "connected")
        # Ordinary scripts do not require any compatibility file.
        config.unlink()
        executable.write_text('#!' + sys.executable + '\nprint("connected")\n')
        with patch.dict(os.environ, {}, clear=True), patch.object(vpn.sys, "platform", "darwin"):
            state, _ = vpn.detect(settings, compatibility_dir=self.target_dir)
        self.assertEqual(state, "connected")

    def test_default_collector_uses_data_directory_mapping(self):
        directory = self.root / "collector"
        directory.mkdir(); install_compat(directory)
        executable = directory / "adapters" / "status"
        executable.write_text('#!' + sys.executable + '\nimport os\nprint("connected" if os.environ.get("' + NEW_ENV + '") == "/opt/example/cli" else "unknown")\n')
        executable.chmod(0o700)
        application = Application(directory)
        try:
            application.store.save_settings({"provider": "script", "status_script_path": str(executable), "tracking_enabled": True})
            with patch.dict(os.environ, {OLD_ENV: "/opt/example/cli"}, clear=True), patch.object(vpn.sys, "platform", "darwin"):
                application.sample()
            self.assertEqual(application.state, "connected")
            self.assertEqual(application.store.export_snapshot()["observations"][-1]["state"], "connected")
        finally:
            application.close()

    def test_old_log_entries_are_normalized_without_accepting_unknown_providers(self):
        events = [
            {"event": "vpn_status", "provider": OLD_SCRIPT, "state": "connected", "message": "fictional"},
            {"event": "vpn_status", "provider": OLD_SYSTEM, "state": "disconnected", "message": "fictional"},
            {"event": "vpn_status", "provider": "unmapped_vendor", "state": "connected", "message": "fictional"},
        ]
        (self.target_dir / "service.log").write_text("".join("2026-01-01T00:00:00+00:00 " + json.dumps(item) + "\n" for item in events))
        entries = self.target.status_log()["entries"]
        self.assertEqual([(row["provider"], row["state"]) for row in entries],
                         [("legacy_script", "connected"), ("verified_system", "disconnected")])


if __name__ == "__main__":
    unittest.main()
