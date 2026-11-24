"""A user-configured local status script; no real VPN is queried."""
import pathlib
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import vpn

SCRIPT = '/tmp/example-status'
SETTINGS = {'provider': 'script', 'status_script_path': SCRIPT, 'tracking_enabled': True}


class StatusScriptTests(unittest.TestCase):
    def setUp(self):
        platform = patch.object(vpn.sys, 'platform', 'darwin')
        platform.start()
        self.addCleanup(platform.stop)

    def test_supported_outputs_and_direct_invocation(self):
        for state in ('connected', 'disconnected', 'unknown'):
            for output in (state, state + '\n'):
                with self.subTest(output=output):
                    runner = Mock(return_value=output)
                    self.assertEqual(vpn.detect(SETTINGS, runner)[0], state)
                    runner.assert_called_once_with([SCRIPT])

    def test_invalid_output_is_unknown_without_logging_raw_output(self):
        for output in ('', 'connected\nPRIVATE_DETAILS', 'CONNECTED', 'reconnecting',
                       '{"connected": true}', ' connected', 'disconnected ', 'unknown\n\n'):
            with self.subTest(output=output):
                state, message = vpn.detect(SETTINGS, Mock(return_value=output))
                self.assertEqual(state, 'unknown')
                self.assertNotIn('PRIVATE_DETAILS', message)
                self.assertNotIn('reconnecting', message)

    def test_real_script_is_directly_invoked_and_cannot_inject_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = pathlib.Path(directory) / 'status $(ignored)'
            executable.write_text('#!' + sys.executable + '\nprint("connected")\n')
            executable.chmod(0o700)
            with patch.object(vpn.subprocess, 'Popen', wraps=vpn.subprocess.Popen) as popen:
                state, _ = vpn.detect({**SETTINGS, 'status_script_path': str(executable)})
            self.assertEqual(state, 'connected')
            args, kwargs = popen.call_args
            self.assertEqual(args[0], [str(executable)])
            self.assertFalse(kwargs.get('shell', False))
            self.assertGreater(vpn.COMMAND_TIMEOUT_SECONDS, 0)
            self.assertLessEqual(vpn.COMMAND_TIMEOUT_SECONDS, 5)

    def test_failed_timed_out_and_oversized_scripts_report_unknown(self):
        bodies = [
            'print("connected", flush=True)\nraise SystemExit(1)\n',
            'import time\nprint("connected", flush=True)\ntime.sleep(10)\n',
            'print("connected" + "x" * 2000, flush=True)\n',
            'import os\nos.write(1, bytes([255]))\n',
        ]
        with tempfile.TemporaryDirectory() as directory:
            executable = pathlib.Path(directory) / 'status'
            for body in bodies:
                executable.write_text('#!' + sys.executable + '\n' + body)
                executable.chmod(0o700)
                with self.subTest(body=body), patch.object(vpn, 'COMMAND_TIMEOUT_SECONDS', 0.3):
                    state, message = vpn.detect({**SETTINGS, 'status_script_path': str(executable)})
                    self.assertEqual(state, 'unknown')
                    self.assertNotIn('connected', message)
                    self.assertNotIn('xxxx', message)
            executable.unlink()
            self.assertEqual(vpn.detect({**SETTINGS, 'status_script_path': str(executable)})[0], 'unknown')

    def test_disabled_collection_never_runs_the_script(self):
        runner = Mock(side_effect=AssertionError('must not execute'))
        self.assertEqual(vpn.detect({**SETTINGS, 'tracking_enabled': False}, runner)[0], 'disabled')
        runner.assert_not_called()

    def test_absolute_path_with_shell_characters_is_a_single_argument(self):
        executable = '/tmp/custom tools/$(ignored)/example-status'
        runner = Mock(return_value='connected\n')
        self.assertEqual(vpn.detect({**SETTINGS, 'status_script_path': executable}, runner)[0], 'connected')
        runner.assert_called_once_with([executable])

    def test_empty_relative_or_null_containing_paths_are_rejected(self):
        for executable in ('', 'example-status', './example-status', '/tmp/null\x00script'):
            with self.subTest(executable=executable):
                runner = Mock(side_effect=AssertionError('must not execute'))
                self.assertEqual(vpn.detect({**SETTINGS, 'status_script_path': executable}, runner)[0], 'unknown')
                runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
