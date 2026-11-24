"""SQLite backups remain bounded-memory, authenticated, and reversible."""
import http.client
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from app import Application, LocalServer, handler_for
from binary_backup import snapshot_file, restore_sqlite_file


class BinaryBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = Application(self.tmp.name, detector=lambda _: ('disabled', 'test'))
        self.app.store.save_settings({'annual_salary': 90000, 'provider':'script', 'status_script_path':'/tmp/example-status', 'tracking_enabled':True})
        now = time.time()
        self.app.store.record(now - 100, 'connected')
        self.app.store.sync(now - 50)
        self.app.store.record(now - 40, 'disconnected')  # pending also preserved
        self.server = LocalServer(('127.0.0.1', 0), handler_for(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval':.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.app.close(); self.tmp.cleanup()

    def request(self, method, path, body=None, *, auth=True, csrf=True, kind=None):
        port = self.server.server_address[1]
        headers = {'Host':f'127.0.0.1:{port}'}
        if auth: headers['X-Session-Token'] = self.app.session_token
        if csrf: headers['X-CSRF-Token'] = self.app.token
        if kind: headers['Content-Type'] = kind
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try:
            conn.request(method,path,body=body,headers=headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally: conn.close()

    def test_download_and_restore_preserve_original_in_rollback(self):
        before = self.app.store.export_snapshot()
        self.assertEqual(self.request('GET','/api/export?format=sqlite',auth=False)[0],401)
        status, headers, backup = self.request('GET','/api/export?format=sqlite')
        self.assertEqual(status,200)
        self.assertTrue(backup.startswith(b'SQLite format 3\x00'))
        self.assertEqual(headers['Content-Type'],'application/vnd.sqlite3')
        self.assertNotIn(self.app.session_token.encode(), backup)
        self.app.store.save_settings({'annual_salary':180000})
        previous = self.app.store.export_snapshot()
        self.assertEqual(self.request('POST','/api/restore-sqlite',backup,csrf=False,kind='application/vnd.sqlite3')[0],403)
        status, _, body = self.request('POST','/api/restore-sqlite',backup,kind='application/vnd.sqlite3')
        self.assertEqual(status,200,body)
        result = json.loads(body)
        current = self.app.store.export_snapshot()
        self.assertEqual(current['observations'],before['observations'])
        self.assertEqual(current['manual_entries'],before['manual_entries'])
        self.assertEqual(current['metadata']['published_seq'],before['metadata']['published_seq'])
        self.assertGreater(current['observations'][-1]['id'],current['metadata']['published_seq'])
        self.assertEqual(current['settings']['annual_salary'],90000)
        self.assertFalse(current['settings']['tracking_enabled'])
        rollback = Path(result['rollback_path'])
        self.assertTrue(rollback.exists())
        self.assertEqual(os.stat(rollback).st_mode & 0o777,0o600)
        with sqlite3.connect(f'file:{rollback}?mode=ro',uri=True) as copy:
            settings = json.loads(copy.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0])
            self.assertEqual(settings['annual_salary'],previous['settings']['annual_salary'])

    def test_invalid_files_and_extra_triggers_are_rejected_without_changes(self):
        before = self.app.store.export_snapshot()
        status, _, _ = self.request('POST','/api/restore-sqlite',b'not sqlite',kind='application/vnd.sqlite3')
        self.assertEqual(status,400)
        self.assertEqual(self.app.store.export_snapshot(),before)
        file = snapshot_file(self.app.store)
        try:
            with sqlite3.connect(file) as source:
                source.execute('CREATE TRIGGER hostile AFTER INSERT ON observations BEGIN DELETE FROM meta; END')
            status, _, _ = self.request('POST','/api/restore-sqlite',file.read_bytes(),kind='application/vnd.sqlite3')
            self.assertEqual(status,400)
            self.assertEqual(self.app.store.export_snapshot(),before)
        finally: file.unlink(missing_ok=True)

    def test_inconsistent_manual_date_is_rejected(self):
        file = snapshot_file(self.app.store)
        try:
            with sqlite3.connect(file) as source:
                source.execute('INSERT INTO manual_entries(date,payload) VALUES (?,?)',
                    ('2041-04-13',json.dumps({'date':'2041-04-12','kind':'daily_total','hours':1,'note':''})))
            before = self.app.store.export_snapshot()
            status, _, _ = self.request('POST','/api/restore-sqlite',file.read_bytes(),kind='application/vnd.sqlite3')
            self.assertEqual(status,400)
            self.assertEqual(self.app.store.export_snapshot(),before)
        finally: file.unlink(missing_ok=True)

    def test_sqlite_prefix_lookalike_trigger_is_not_an_internal_object(self):
        file = snapshot_file(self.app.store)
        try:
            with sqlite3.connect(file) as source:
                source.execute('CREATE TRIGGER sqliteXevil AFTER INSERT ON observations BEGIN DELETE FROM meta; END')
            before = self.app.store.export_snapshot()
            status, _, _ = self.request('POST','/api/restore-sqlite',file.read_bytes(),kind='application/vnd.sqlite3')
            self.assertEqual(status,400)
            self.assertEqual(self.app.store.export_snapshot(),before)
        finally: file.unlink(missing_ok=True)

    def test_forged_reserved_name_is_not_ignored(self):
        file = snapshot_file(self.app.store)
        try:
            with sqlite3.connect(file) as source:
                source.execute('CREATE TRIGGER untrusted AFTER INSERT ON observations BEGIN DELETE FROM meta; END')
                source.execute('PRAGMA writable_schema=ON')
                source.execute("UPDATE sqlite_master SET name='sqlite_untrusted' WHERE name='untrusted'")
                source.execute('PRAGMA writable_schema=OFF')
            before = self.app.store.export_snapshot()
            status, _, _ = self.request('POST','/api/restore-sqlite',file.read_bytes(),kind='application/vnd.sqlite3')
            self.assertEqual(status,400)
            self.assertEqual(self.app.store.export_snapshot(),before)
        finally: file.unlink(missing_ok=True)

    def test_binary_does_not_inherit_json_size_limit(self):
        with patch('exporting.MAX_BACKUP_BYTES',10):
            self.assertEqual(self.request('GET','/api/export?format=json')[0],413)
            self.assertEqual(self.request('GET','/api/export?format=sqlite')[0],200)

    def test_rollback_write_failure_does_not_replace_data(self):
        path = snapshot_file(self.app.store)
        try:
            before = self.app.store.export_snapshot()
            with patch('binary_backup.snapshot_file', side_effect=OSError('disk full')):
                with self.assertRaises(OSError): restore_sqlite_file(self.app,path)
            self.assertEqual(self.app.store.export_snapshot(),before)
        finally: path.unlink(missing_ok=True)

    def test_untrusted_autoincrement_sequence_is_rebuilt_from_real_rows(self):
        file = snapshot_file(self.app.store)
        try:
            expected = max(s['id'] for s in self.app.store.export_snapshot()['observations'])
            with sqlite3.connect(file) as source:
                source.execute("UPDATE sqlite_sequence SET seq=9223372036854775807 WHERE name='observations'")
            status, _, body = self.request('POST','/api/restore-sqlite',file.read_bytes(),kind='application/vnd.sqlite3')
            self.assertEqual(status, 200, body)
            self.app.store.record(time.time(), 'connected')
            self.app.store.record(time.time() + 1, 'disconnected')
            ids = [s['id'] for s in self.app.store.export_snapshot()['observations']]
            self.assertEqual(ids[-2:], [expected + 1, expected + 2])
        finally: file.unlink(missing_ok=True)

    def test_nearly_exhausted_observation_ids_are_rejected(self):
        file = snapshot_file(self.app.store)
        try:
            with sqlite3.connect(file) as source:
                source.execute("INSERT INTO observations(id,ts,state) VALUES(?,?,?)", (2**62, time.time(), 'connected'))
            before = self.app.store.export_snapshot()
            status, _, _ = self.request('POST','/api/restore-sqlite',file.read_bytes(),kind='application/vnd.sqlite3')
            self.assertEqual(status, 400)
            self.assertEqual(self.app.store.export_snapshot(), before)
        finally: file.unlink(missing_ok=True)
