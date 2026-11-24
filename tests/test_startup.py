"""Process-level startup checks; temporary data and a fake VPN detector only."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instance import AlreadyRunning, InstanceLock, is_locked
import launcher
from store import Store

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ID = '11111111-2222-3333-4444-555555555555'
FAKE_SERVER = '''import app
original = app.Application
def fake_application(directory):
    return original(directory, detector=lambda settings: (
        ("connected", "test connected") if settings["tracking_enabled"]
        else ("disabled", "test disabled")))
app.Application = fake_application
app.main()
'''


def snapshot(directory):
    with sqlite3.connect(Path(directory) / 'records.sqlite3') as connection:
        # Compare every table, not only the collector's observations and meta:
        # a duplicate process must not alter manual records or sleep data either.
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        schema = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        data = tuple((table, connection.execute(
            'SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid').fetchall())
                     for table in tables)
        return schema, data


class InstanceLockTests(unittest.TestCase):
    def test_directory_lock_rejects_second_owner_and_preserves_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            with InstanceLock(directory):
                inode = (Path(directory) / 'instance.lock').stat().st_ino
                with self.assertRaises(AlreadyRunning):
                    with InstanceLock(directory):
                        self.fail('Second owner must be rejected')
            with InstanceLock(directory):
                self.assertEqual((Path(directory) / 'instance.lock').stat().st_ino, inode)


class BrowserSelectionTests(unittest.TestCase):
    def test_opens_named_app_without_shell_or_logging_credentials(self):
        access = {'url': 'http://127.0.0.1:1234', 'session_token': 'test-session', 'pair_token': 'test-pair'}
        with patch.object(launcher.sys, 'platform', 'darwin'), \
             patch.object(launcher.subprocess, 'run') as run:
            run.return_value.returncode = 0
            launcher.open_browser(access, 'Example Browser')
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['/usr/bin/open', '-a', 'Example Browser',
                                   'http://127.0.0.1:1234/#access=test-session&pair=test-pair'])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)

    def test_default_browser_still_uses_standard_launcher(self):
        access = {'url': 'http://127.0.0.1:1234', 'session_token': 'test-session', 'pair_token': ''}
        with patch.object(launcher.webbrowser, 'open', return_value=True) as opened:
            launcher.open_browser(access)
        opened.assert_called_once_with('http://127.0.0.1:1234/#access=test-session')

    def test_failed_open_does_not_include_private_link_in_error(self):
        access = {'url': 'http://127.0.0.1:1234', 'session_token': 'secret-session', 'pair_token': 'secret-pair'}
        with patch.object(launcher.sys, 'platform', 'darwin'), \
             patch.object(launcher.subprocess, 'run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(SystemExit) as raised:
                launcher.open_browser(access, 'Missing Browser')
        self.assertNotIn('secret', str(raised.exception))


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / 'data'
        self.processes = []
        self.gate = None
        self.child_env = None

    def tearDown(self):
        # Always unblock the collector before terminating a service, including
        # on failed assertions or timeouts.
        self.release_collector()
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            process.communicate()
        self.temporary.cleanup()

    def command(self, port=0):
        return [sys.executable, '-c', FAKE_SERVER, '--port', str(port), '--data-dir', str(self.directory)]

    def start_server(self):
        process = subprocess.Popen(self.command(), cwd=ROOT, env=self.child_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        for _ in range(100):
            access = launcher.running(self.directory)
            if access is not None:
                return process, access
            if process.poll() is not None:
                self.fail('Service failed to start: ' + process.communicate()[1])
            time.sleep(0.05)
        self.fail('Service did not become ready')

    def gate_initial_sync(self):
        """Block only the isolated child service's first sync, not HTTP or launcher."""
        self.gate = Path(self.temporary.name) / 'sync-gate'
        self.gate.mkdir()
        bootstrap = Path(self.temporary.name) / 'child-bootstrap'
        bootstrap.mkdir()
        # Python imports sitecustomize in the isolated child before app.py or
        # the -c FAKE_SERVER. launcher.py itself is deliberately not patched.
        (bootstrap / 'sitecustomize.py').write_text('''\
import os, sys, time
from pathlib import Path
if os.path.basename(sys.argv[0]) in ("app.py", "-c"):
    gate = Path(os.environ["HOURLY_RATE_STARTUP_TEST_GATE"])
    if os.path.basename(sys.argv[0]) == "app.py":
        (gate / ("process-" + str(os.getpid()))).touch()
        deadline = time.monotonic() + 30
        while (gate / "hold-startup").exists() and not (gate / "release-startup").exists():
            if time.monotonic() >= deadline:
                (gate / "timeout").touch()
                raise RuntimeError("test startup gate timed out")
            time.sleep(0.01)
    from store import Store
    original_init = Store.__init__
    def probed_init(self, *args, **kwargs):
        gate = Path(os.environ["HOURLY_RATE_STARTUP_TEST_GATE"])
        (gate / ("init-" + str(os.getpid()))).touch()
        return original_init(self, *args, **kwargs)
    Store.__init__ = probed_init
    original_sync = Store.sync
    def gated_sync(self, *args, **kwargs):
        gate = Path(os.environ["HOURLY_RATE_STARTUP_TEST_GATE"])
        (gate / "waiting").touch()
        deadline = time.monotonic() + 30
        while not (gate / "release").exists():
            if time.monotonic() >= deadline:
                (gate / "timeout").touch()
                raise RuntimeError("test sync gate timed out")
            time.sleep(0.01)
        result = original_sync(self, *args, **kwargs)
        (gate / "synced").touch()
        return result
    Store.sync = gated_sync
''', encoding='utf-8')
        self.child_env = dict(os.environ)
        self.child_env['HOURLY_RATE_STARTUP_TEST_GATE'] = str(self.gate)
        self.child_env['PYTHONPATH'] = os.pathsep.join(filter(None, (
            str(bootstrap), str(ROOT), self.child_env.get('PYTHONPATH', ''))))

    def wait_for_gate(self, marker, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (self.gate / 'timeout').exists():
                self.fail('Collector sync gate timed out')
            if (self.gate / marker).exists():
                return
            time.sleep(0.01)
        self.fail('Collector sync gate did not reach ' + marker)

    def release_collector(self):
        if self.gate is not None and self.gate.exists():
            (self.gate / 'release').touch()
            (self.gate / 'release-startup').touch()

    def owned_service_children(self):
        """Find only app.py children using this test's unique data directory."""
        if self.gate is None or not self.gate.exists():
            return [], []
        owned, unknown = [], []
        # A detached child may be delayed before it can write its own marker.
        # Find it by command and unique directory as well as by marker.
        try:
            listing = subprocess.run(['/bin/ps', '-axo', 'pid=,command='],
                                     capture_output=True, text=True, timeout=2, check=True)
            for line in listing.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and str(ROOT / 'app.py') in parts[1] and str(self.directory) in parts[1]:
                    owned.append(int(parts[0]))
        except (OSError, ValueError, subprocess.SubprocessError):
            unknown.append('process listing unavailable')
        for marker in self.gate.glob('process-*'):
            try:
                pid = int(marker.name.removeprefix('process-'))
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    unknown.append(pid)
                    continue
                result = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'command='],
                                        capture_output=True, text=True, timeout=2)
                command = result.stdout
                if result.returncode == 0 and str(ROOT / 'app.py') in command and str(self.directory) in command:
                    if pid not in owned:
                        owned.append(pid)
                elif result.returncode != 0:
                    unknown.append(pid)
            except ValueError:
                continue
            except (OSError, subprocess.SubprocessError):
                unknown.append(pid)
        return owned, unknown

    def stop_gated_service(self):
        """Allow an in-flight child to become ready, then stop only this test's service."""
        self.release_collector()
        started = time.monotonic()
        deadline = started + 10
        stop_error = None
        while time.monotonic() < deadline:
            if stop_error is None and launcher.running(self.directory):
                try:
                    launcher.stop(self.directory)
                except (Exception, SystemExit) as error:
                    # A failing stop must not skip cleanup of detached test
                    # children. Preserve the failure after cleanup completes.
                    stop_error = error
            # A detached child may not yet have acquired its directory lock.
            # Give it a short grace period even if it has not reported in yet.
            owned, unknown = self.owned_service_children()
            if time.monotonic() - started >= 2.0 and not owned and not unknown and not is_locked(self.directory):
                if stop_error is not None:
                    self.fail(f'Failed to stop isolated test service: {stop_error}')
                return
            time.sleep(0.05)
        children, unknown = self.owned_service_children()
        for pid in children:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        limit = time.monotonic() + 3
        while self.owned_service_children()[0] and time.monotonic() < limit:
            time.sleep(0.05)
        for pid in self.owned_service_children()[0]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.fail('Timed out stopping isolated test service; verified children were terminated; '
                  f'children that could not be verified: {unknown}; stop error: {stop_error}')

    def initialized_children(self):
        return {path.name for path in self.gate.glob('init-*')}

    def assert_first_sync_completed(self, before):
        self.wait_for_gate('synced')
        old_tables = dict(before[1])
        old_meta = dict(old_tables['meta'])
        self.assertNotIn('last_synced_at', old_meta)
        self.assertNotIn('published_seq', old_meta)
        with sqlite3.connect(self.directory / 'records.sqlite3') as connection:
            meta = dict(connection.execute('SELECT key,value FROM meta'))
        synced_at = json.loads(meta['last_synced_at'])
        published = json.loads(meta['published_seq'])
        self.assertIsInstance(synced_at, (int, float))
        self.assertGreater(synced_at, 0)
        self.assertGreaterEqual(published, max((row[0] for row in old_tables['observations']), default=0))
        self.assertIsNotNone(launcher.running(self.directory))

    def seed(self, tracking=False):
        store = Store(self.directory)
        try:
            store.save_settings({'annual_salary': 123456, 'provider': 'system',
                                 'service_id': SERVICE_ID, 'tracking_enabled': tracking})
            store.record(time.time() - 30, 'connected')
            store.save_manual_entries([{'date':'2020-01-01','kind':'daily_total','hours':8}])
        finally:
            store.close()

    def test_snapshot_detects_manual_data_and_schema_writes(self):
        self.seed()
        before = snapshot(self.directory)
        # Verify the duplicate-start oracle actually detects changes outside
        # observations/meta, as well as schema changes, in a disposable DB.
        with sqlite3.connect(self.directory / 'records.sqlite3') as connection:
            connection.execute('CREATE INDEX test_manual_index ON manual_entries(date)')
        self.assertNotEqual(snapshot(self.directory), before)
        with sqlite3.connect(self.directory / 'records.sqlite3') as connection:
            connection.execute('DROP INDEX test_manual_index')
        self.assertEqual(snapshot(self.directory), before)
        with sqlite3.connect(self.directory / 'records.sqlite3') as connection:
            payload = json.loads(connection.execute('SELECT payload FROM manual_entries').fetchone()[0])
            payload['hours'] = 9
            connection.execute('UPDATE manual_entries SET payload=?', (json.dumps(payload),))
        self.assertNotEqual(snapshot(self.directory), before)

    def test_cleanup_handles_child_not_yet_ready(self):
        self.gate_initial_sync()
        (self.gate / 'hold-startup').touch()
        command = [sys.executable, str(ROOT / 'launcher.py'), '--data-dir', str(self.directory), '--port', '0', '--no-browser']
        process = subprocess.Popen(command, cwd=ROOT, env=self.child_env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 8
            while not list(self.gate.glob('process-*')) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(list(self.gate.glob('process-*')), 'Detached child did not start')
            self.assertIsNone(launcher.running(self.directory))
        finally:
            try:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
            finally:
                self.stop_gated_service()
        self.assertFalse(is_locked(self.directory))

    def test_cleanup_checks_for_other_children_after_stopping_ready_service(self):
        self.gate_initial_sync()
        # Even after the ready service stops, a buggy duplicate could still be
        # starting. Do not skip the child scan on that failure path.
        with patch.object(launcher, 'running', return_value={'url': 'test'}), \
             patch.object(launcher, 'stop') as stop, \
             patch.object(self, 'owned_service_children', return_value=([], [])) as children, \
             patch.object(sys.modules[__name__], 'is_locked', return_value=False), \
             patch.object(time, 'monotonic', side_effect=[0, 0, 3]):
            self.stop_gated_service()
        stop.assert_called_once_with(self.directory)
        children.assert_called_once()

    def test_cleanup_scans_children_even_when_stopping_service_fails(self):
        self.gate_initial_sync()
        with patch.object(launcher, 'running', return_value={'url': 'test'}), \
             patch.object(launcher, 'stop', side_effect=SystemExit('stop failed')), \
             patch.object(self, 'owned_service_children', return_value=([], [])) as children, \
             patch.object(sys.modules[__name__], 'is_locked', return_value=False), \
             patch.object(time, 'monotonic', side_effect=[0, 0, 3]):
            with self.assertRaisesRegex(AssertionError, 'stop failed'):
                self.stop_gated_service()
        children.assert_called_once()

    def test_duplicate_same_and_different_ports_leave_records_and_credentials_unchanged(self):
        self.seed(tracking=True)
        self.gate_initial_sync()
        process, access = self.start_server()
        # HTTP can become ready while the first sync is still pending. Hold
        # that sync (and its collector lock) until duplicate checks complete,
        # so legitimate samples and power events cannot race the snapshots.
        self.wait_for_gate('waiting')
        self.assertFalse((self.gate / 'synced').exists())
        initialized = self.initialized_children()
        self.assertEqual(len(initialized), 1)
        original = snapshot(self.directory)
        original_access = (self.directory / 'access.json').read_bytes()
        port = int(access['url'].rsplit(':', 1)[1])
        for duplicate_port in (port, 0):
            with self.subTest(port=duplicate_port):
                duplicate = subprocess.run(self.command(duplicate_port), cwd=ROOT, env=self.child_env,
                                           capture_output=True, text=True, timeout=5)
                self.assertNotEqual(duplicate.returncode, 0)
                self.assertIn('已有服务', duplicate.stderr)
                self.assertEqual(self.initialized_children(), initialized)
                self.assertEqual(snapshot(self.directory), original)
                self.assertEqual((self.directory / 'access.json').read_bytes(), original_access)
                self.assertIsNone(process.poll())
        self.assertFalse((self.gate / 'synced').exists())
        self.release_collector()
        self.assert_first_sync_completed(original)
        self.assertIsNone(process.poll())
        # Also exercise an already-running service after startup. The live
        # collector may legitimately write now, so check process identity and
        # initialization rather than comparing a moving database snapshot.
        duplicate = subprocess.run(self.command(0), cwd=ROOT, env=self.child_env,
                                   capture_output=True, text=True, timeout=5)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn('已有服务', duplicate.stderr)
        self.assertEqual(self.initialized_children(), initialized)
        self.assertEqual((self.directory / 'access.json').read_bytes(), original_access)
        self.assertIsNone(process.poll())
        launcher.stop(self.directory)
        process.wait(timeout=5)
        self.assertFalse(is_locked(self.directory))
        self.assertFalse((self.directory / 'access.json').exists())
        self.start_server()

    def test_login_item_sessions_append_real_status_logs_to_existing_service_log(self):
        self.directory.mkdir(parents=True)
        log = self.directory / 'service.log'
        log.write_text('old log before login\n')
        env = dict(os.environ, HOURLY_RATE_LOGIN_ITEM='1')
        for _ in range(2):
            process = subprocess.Popen(self.command(), cwd=ROOT, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.processes.append(process)
            for _ in range(100):
                if launcher.running(self.directory) is not None:
                    break
                if process.poll() is not None:
                    self.fail('Login item service failed: ' + process.communicate()[1])
                time.sleep(0.05)
            else:
                self.fail('Login item service did not become ready')
            launcher.stop(self.directory)
            process.wait(timeout=5)
        content = log.read_text()
        self.assertTrue(content.startswith('old log before login\n'))
        self.assertGreaterEqual(content.count('"event": "vpn_status"'), 2)

    def test_occupied_port_does_not_create_database(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            result = subprocess.run(self.command(listener.getsockname()[1]), cwd=ROOT, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('端口已占用', result.stderr)
        self.assertFalse((self.directory / 'records.sqlite3').exists())
        self.assertFalse((self.directory / 'access.json').exists())
        self.assertFalse(is_locked(self.directory))

    def test_occupied_port_does_not_modify_existing_database(self):
        self.seed(tracking=True)
        before = (self.directory / 'records.sqlite3').read_bytes()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            result = subprocess.run(self.command(listener.getsockname()[1]), cwd=ROOT, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.directory / 'records.sqlite3').read_bytes(), before)

    def test_stale_credentials_are_not_treated_as_a_running_service(self):
        self.start_server()
        path = self.directory / 'access.json'
        original = path.read_text()
        access = json.loads(original)
        access['session_token'] = 'stale-session'
        path.write_text(json.dumps(access))
        try:
            self.assertIsNone(launcher.running(self.directory))
        finally:
            path.write_text(original)

    def test_launcher_waits_for_previous_owner_to_release_directory(self):
        # Model a service whose HTTP listener has closed but whose database
        # cleanup still owns the directory. Startup must wait and then proceed.
        previous = InstanceLock(self.directory)
        previous.__enter__()
        release = threading.Timer(0.2, previous.__exit__)
        release.start()
        spawn = subprocess.Popen

        def keep_child(*args, **kwargs):
            process = spawn(*args, **kwargs)
            self.processes.append(process)
            return process

        try:
            with patch.object(launcher.subprocess, 'Popen', side_effect=keep_child):
                access = launcher.start(self.directory, 0)
            self.assertIsNotNone(access)
            self.assertTrue(is_locked(self.directory))
        finally:
            release.join()
            previous.__exit__()
            if launcher.running(self.directory):
                launcher.stop(self.directory)

    def test_concurrent_launchers_reuse_one_service_and_can_stop_it(self):
        self.seed()
        self.gate_initial_sync()
        command = [sys.executable, str(ROOT / 'launcher.py'), '--data-dir', str(self.directory), '--port', '0', '--no-browser']
        first = subprocess.Popen(command, cwd=ROOT, env=self.child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command, cwd=ROOT, env=self.child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for process in (first, second):
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stdout + stderr)
            access = launcher.running(self.directory)
            self.assertIsNotNone(access)
            self.wait_for_gate('waiting')
            self.assertFalse((self.gate / 'synced').exists())
            initialized = self.initialized_children()
            self.assertEqual(len(initialized), 1)
            original = snapshot(self.directory)
            original_access = (self.directory / 'access.json').read_bytes()
            result = subprocess.run(command, cwd=ROOT, env=self.child_env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.initialized_children(), initialized)
            self.assertEqual((self.directory / 'access.json').read_bytes(), original_access)
            self.assertEqual(snapshot(self.directory), original)
            self.assertFalse((self.gate / 'synced').exists())
            self.release_collector()
            self.assert_first_sync_completed(original)
            self.assertEqual((self.directory / 'access.json').read_bytes(), original_access)
            repeated = subprocess.run(command, cwd=ROOT, env=self.child_env,
                                      capture_output=True, text=True, timeout=5)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(self.initialized_children(), initialized)
            self.assertEqual((self.directory / 'access.json').read_bytes(), original_access)
            self.assertIsNotNone(launcher.running(self.directory))
        finally:
            self.release_collector()
            try:
                for process in (first, second):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.communicate(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate(timeout=5)
            finally:
                self.stop_gated_service()
        self.assertFalse(is_locked(self.directory))
