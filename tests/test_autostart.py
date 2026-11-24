"""Login item changes are tested in temporary directories with a fake launchctl."""
import os
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autostart import LABEL, AutostartError, LoginItem
from app import _login_log_stream


class FakeLaunchctl:
    def __init__(self):
        self.disabled = False
        self.calls = []
        self.fail = None
        self.output = None

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        action = argv[1]
        if self.fail == action:
            return SimpleNamespace(returncode=1, stdout="", stderr="failed")
        if action == "enable": self.disabled = False
        if action == "disable": self.disabled = True
        stdout = self.output if self.output is not None else (
            'disabled services = {\n"' + LABEL + '" => ' +
            ('disabled' if self.disabled else 'enabled') + '\n}')
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


class LoginItemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data = self.base / "data with spaces $()"
        self.data.mkdir()
        (self.data / 'adapters').mkdir()
        (self.data / 'adapters' / 'legacy-compat.json').write_text(json.dumps({
            'version': 1, 'providers': {},
            'environment': {'HOURLY_RATE_OLD_CLI': 'HOURLY_RATE_ADAPTER_LEGACY_PATH'},
        }))
        (self.base / 'project with spaces').mkdir()
        (self.base / 'project with spaces' / 'app.py').write_text('')
        self.runner = FakeLaunchctl()
        self.options = dict(home=self.base, root=self.base / 'project with spaces',
                            executable='/usr/bin/python3', platform='darwin',
                            environment={'HOURLY_RATE_OLD_CLI': '/opt/Custom VPN/cli'},
                            runner=self.runner, uid=501)
        self.item = LoginItem(self.data, 8765, **self.options)

    def test_toggle_preserves_current_data_and_uses_direct_foreground_app(self):
        sentinel = self.data / 'records.sqlite3'
        sentinel.write_bytes(b'unchanged')
        self.assertFalse(self.item.status()['enabled'])
        self.assertTrue(self.item.set_enabled(True)['enabled'])
        with self.item.path.open('rb') as stream:
            job = plistlib.load(stream)
        self.assertEqual(job['ProgramArguments'], [str(Path('/usr/bin/python3').resolve()),
            str(self.base / 'project with spaces' / 'app.py'), '--data-dir', str(self.data), '--port', '8765'])
        self.assertEqual(job['EnvironmentVariables']['HOURLY_RATE_ADAPTER_LEGACY_PATH'], '/opt/Custom VPN/cli')
        self.assertTrue(job['RunAtLoad'])
        self.assertNotIn('KeepAlive', job)
        self.assertEqual(job['EnvironmentVariables']['HOURLY_RATE_LOGIN_ITEM'], '1')
        self.assertEqual(job['StandardErrorPath'], str(self.data / 'autostart-diagnostics.log'))
        self.assertEqual(job['StandardOutPath'], str(self.data / 'autostart-startup.log'))
        self.assertEqual(self.item.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.item.set_enabled(False)['enabled'])
        self.assertFalse(self.item.path.exists())
        self.assertEqual(sentinel.read_bytes(), b'unchanged')
        self.assertNotIn('bootout', [x[1] for x in self.runner.calls])

    def test_system_disable_and_unreadable_state_are_not_reported_enabled(self):
        self.item.set_enabled(True)
        self.runner.disabled = True
        self.assertIs(self.item.status()['enabled'], False)
        self.runner.fail = 'print-disabled'
        self.assertIsNone(self.item.status()['enabled'])
        self.runner.fail = None
        self.runner.output = ''
        self.assertIsNone(self.item.status()['enabled'])

    def test_other_directory_is_not_reported_enabled(self):
        self.item.set_enabled(True)
        other = LoginItem(self.base / 'different', 8765, **self.options)
        self.assertFalse(other.status()['enabled'])
        self.assertIn('其他项目或数据目录', other.status()['message'])

    def test_missing_program_or_nonautomatic_job_is_not_reported_enabled(self):
        self.item.set_enabled(True)
        script = self.item.root / 'app.py'
        script.unlink()
        self.assertFalse(self.item.status()['enabled'])
        script.write_text('')
        with self.item.path.open('rb') as stream:
            job = plistlib.load(stream)
        job['RunAtLoad'] = False
        self.item.path.write_bytes(plistlib.dumps(job))
        self.assertFalse(self.item.status()['enabled'])

    def test_foreign_file_and_symlink_are_never_replaced_or_removed(self):
        self.item.path.parent.mkdir(parents=True)
        self.item.path.write_bytes(plistlib.dumps({'Label': LABEL, 'ProgramArguments': ['/other']}))
        before = self.item.path.read_bytes()
        for value in (True, False):
            with self.assertRaises(AutostartError): self.item.set_enabled(value)
        self.assertEqual(before, self.item.path.read_bytes())
        self.item.path.unlink()
        target = self.base / 'foreign'
        target.write_text('keep')
        self.item.path.symlink_to(target)
        with self.assertRaises(AutostartError): self.item.set_enabled(True)
        self.assertEqual(target.read_text(), 'keep')

    def test_enable_failure_does_not_install_plist(self):
        self.runner.fail = 'enable'
        with self.assertRaises(AutostartError): self.item.set_enabled(True)
        self.assertFalse(self.item.path.exists())

    def test_replace_failure_restores_previous_system_disabled_state(self):
        self.runner.disabled = True
        with patch('autostart.os.replace', side_effect=OSError('test')):
            with self.assertRaises(OSError): self.item.set_enabled(True)
        self.assertTrue(self.runner.disabled)
        self.assertFalse(self.item.path.exists())

    def test_replace_failure_reports_failed_system_rollback(self):
        self.runner.disabled = True
        self.runner.fail = 'disable'
        with patch('autostart.os.replace', side_effect=OSError('test')):
            with self.assertRaisesRegex(AutostartError, '系统状态恢复失败'):
                self.item.set_enabled(True)

    def test_unknown_platform_and_invalid_values(self):
        item = LoginItem(self.data, 8765, **{**self.options, 'platform': 'linux'})
        self.assertFalse(item.status()['supported'])
        with self.assertRaises(AutostartError): item.set_enabled(True)
        with self.assertRaises(AutostartError): self.item.set_enabled('true')

    def test_launchctl_timeout_gives_unknown_without_mutation(self):
        self.item.set_enabled(True)
        self.item.runner = lambda *args, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired('launchctl', 5))
        self.assertIsNone(self.item.status()['enabled'])
        self.assertTrue(self.item.path.exists())

    def test_login_sessions_append_to_the_existing_manual_service_log(self):
        log = self.data / 'service.log'
        log.write_text('manual log\n')
        for line in ('first login\n', 'second login\n'):
            with _login_log_stream(self.data) as stream:
                stream.write(line)
        self.assertEqual(log.read_text(), 'manual log\nfirst login\nsecond login\n')
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
