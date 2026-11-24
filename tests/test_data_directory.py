import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from data_directory import (DirectoryError, default_paths, locked_data_directory, migrate_default_directory,
                            recover_default_directory, resolve_data_directory)
from instance import InstanceLock


class DataDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.old, self.new, self.marker = default_paths(self.home)
        self.old.mkdir(parents=True, mode=0o700)

    def test_old_is_used_until_explicit_migration(self):
        self.assertEqual(resolve_data_directory(home=self.home), self.old)
        self.assertEqual(resolve_data_directory(self.old, home=self.home), self.old)
        with self.assertRaises(DirectoryError):
            resolve_data_directory(self.new, home=self.home)
        self.assertFalse(self.new.exists())

    def test_fresh_install_uses_new_name(self):
        self.old.rmdir()
        self.assertEqual(resolve_data_directory(home=self.home), self.new)
        self.assertFalse(self.new.exists())

    def test_preserves_database_wal_credentials_adapter_and_permissions(self):
        db = self.old / 'records.sqlite3'
        source = '''import os, sqlite3, sys\nc=sqlite3.connect(sys.argv[1]); c.execute("PRAGMA journal_mode=WAL"); c.execute("CREATE TABLE history (value TEXT)"); c.execute("INSERT INTO history VALUES ('old record')"); c.commit(); os._exit(0)'''
        subprocess.run([sys.executable, '-c', source, str(db)], check=True)
        wal = self.old / 'records.sqlite3-wal'
        self.assertTrue(wal.is_file())
        adapter = self.old / 'adapters' / 'status'
        adapter.parent.mkdir()
        adapter.write_text('#!/bin/sh\nexit 0\n')
        adapter.chmod(0o700)
        (self.old / 'access.json').write_text('{"fake": true}')
        inode = db.stat().st_ino
        self.assertEqual(migrate_default_directory(home=self.home), 'migrated')
        self.assertTrue(self.old.is_symlink())
        self.assertEqual(os.readlink(self.old), 'HourlyRate')
        self.assertEqual((self.new / 'records.sqlite3').stat().st_ino, inode)
        self.assertTrue((self.new / wal.name).exists())
        self.assertEqual((self.old / 'adapters' / 'status').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.new / 'access.json').read_text(), '{"fake": true}')
        self.assertFalse(self.marker.exists())
        with sqlite3.connect(self.new / db.name) as connection:
            self.assertEqual(connection.execute('SELECT value FROM history').fetchall(), [('old record',)])
        self.assertEqual(resolve_data_directory(home=self.home), self.new.resolve())
        self.assertEqual(resolve_data_directory(self.old, home=self.home), self.new.resolve())
        self.assertEqual(migrate_default_directory(home=self.home), 'already-migrated')

    def test_refuses_active_instance_and_launcher(self):
        for lock_name in ('instance.lock', 'launcher.lock'):
            with self.subTest(lock=lock_name), InstanceLock(self.old, name=lock_name):
                with self.assertRaises(DirectoryError):
                    migrate_default_directory(home=self.home)
                self.assertTrue(self.old.is_dir())
                self.assertFalse(self.new.exists())
                self.assertFalse(self.marker.exists())

    def test_conflicting_directories_and_unknown_symlinks_fail_closed(self):
        self.new.mkdir()
        (self.old / 'old').write_text('old')
        (self.new / 'new').write_text('new')
        for choice in (None, self.old, self.new):
            with self.subTest(choice=choice), self.assertRaises(DirectoryError):
                resolve_data_directory(choice, home=self.home)
        with self.assertRaises(DirectoryError):
            migrate_default_directory(home=self.home)
        self.assertEqual((self.old / 'old').read_text(), 'old')
        self.assertEqual((self.new / 'new').read_text(), 'new')

    def test_recover_after_interruption_before_move(self):
        with patch('data_directory._rename_exclusive', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                migrate_default_directory(home=self.home)
        self.assertTrue(self.marker.exists())
        with self.assertRaises(DirectoryError):
            resolve_data_directory(home=self.home)
        self.assertEqual(recover_default_directory(home=self.home), 'not-started')
        self.assertEqual(resolve_data_directory(home=self.home), self.old)

    def test_recover_after_move_before_alias(self):
        (self.old / 'record').write_text('fake history')
        with patch('data_directory.os.symlink', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                migrate_default_directory(home=self.home)
        self.assertTrue(self.marker.exists())
        self.assertFalse(self.old.exists())
        self.assertEqual((self.new / 'record').read_text(), 'fake history')
        with self.assertRaises(DirectoryError):
            resolve_data_directory(home=self.home)
        self.assertEqual(recover_default_directory(home=self.home), 'needs-alias')
        self.assertEqual((self.old / 'record').read_text(), 'fake history')
        self.assertFalse(self.marker.exists())

    def test_recover_after_alias_before_marker_removed(self):
        with patch('data_directory._remove_marker', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                migrate_default_directory(home=self.home)
        self.assertTrue(self.old.is_symlink())
        with self.assertRaises(DirectoryError):
            resolve_data_directory(home=self.home)
        self.assertEqual(recover_default_directory(home=self.home), 'completed')
        self.assertEqual(resolve_data_directory(home=self.home), self.new.resolve())

    def test_recovery_refuses_conflict_and_active_target(self):
        with patch('data_directory.os.symlink', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                migrate_default_directory(home=self.home)
        with InstanceLock(self.new):
            with self.assertRaises(DirectoryError):
                recover_default_directory(home=self.home)
        self.old.mkdir()
        with self.assertRaises(DirectoryError):
            recover_default_directory(home=self.home)
        self.assertTrue(self.marker.exists())
        self.assertTrue(self.new.exists())

    def test_resolution_and_lock_wait_for_guarded_migration(self):
        import data_directory
        original = data_directory._rename_exclusive
        moving = threading.Event()
        release = threading.Event()
        selected = []
        errors = []
        def delayed_move(old, new):
            moving.set()
            if not release.wait(3):
                raise AssertionError('test did not release migration')
            original(old, new)
        def move():
            try:
                with patch('data_directory._rename_exclusive', side_effect=delayed_move):
                    migrate_default_directory(home=self.home)
            except BaseException as error:
                errors.append(error)
        def start():
            try:
                with locked_data_directory(home=self.home, timeout=2) as lock:
                    selected.append(lock.directory)
            except BaseException as error:
                errors.append(error)
        migration = threading.Thread(target=move)
        migration.start()
        try:
            self.assertTrue(moving.wait(2))
            startup = threading.Thread(target=start)
            startup.start()
            time.sleep(0.1)
            self.assertEqual(selected, [])
        finally:
            release.set()
            migration.join(3)
        startup.join(3)
        self.assertFalse(migration.is_alive())
        self.assertFalse(startup.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(selected, [self.new.resolve()])
        self.assertTrue(self.old.is_symlink())

    def test_waiting_launcher_does_not_block_service_child(self):
        acquired = threading.Event()
        errors = []
        def competing_launcher():
            try:
                with locked_data_directory(home=self.home, name='launcher.lock', timeout=2):
                    acquired.set()
            except BaseException as error:
                errors.append(error)
        with locked_data_directory(home=self.home, name='launcher.lock'):
            thread = threading.Thread(target=competing_launcher)
            thread.start()
            time.sleep(0.1)
            with locked_data_directory(home=self.home, name='instance.lock', timeout=1):
                self.assertFalse(acquired.is_set())
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(acquired.is_set())

    def test_alias_to_default_is_blocked_by_incomplete_marker(self):
        alias = self.home / 'my-alias'
        alias.symlink_to(self.old)
        self.marker.write_bytes(b'hourly-rate-directory-migration-v1\n')
        with self.assertRaises(DirectoryError):
            with locked_data_directory(alias, home=self.home):
                pass

    def test_custom_directories_not_affected(self):
        custom = self.home / 'my-data'
        self.new.mkdir()
        self.assertEqual(resolve_data_directory(custom, home=self.home), custom)


if __name__ == '__main__':
    unittest.main()
