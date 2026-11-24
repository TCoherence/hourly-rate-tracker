"""Sleep/wake notification mocks; never suspend, wake or configure the machine."""

import ctypes
import pathlib
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import power


class FakeNotifications:
    def __init__(self, callback):
        self.callback = callback
        self.closed = False
        self.polling = threading.Event()

    def open(self):
        pass

    def poll(self):
        self.polling.set()
        threading.Event().wait(0.005)

    def close(self):
        self.closed = True


class PowerMonitorTests(unittest.TestCase):
    def setUp(self):
        self.platform = patch.object(power.sys, "platform", "darwin")
        self.platform.start()
        self.addCleanup(self.platform.stop)

    def monitor(self, callback=None):
        monitor = power.PowerMonitor(callback or Mock())
        self.addCleanup(monitor.stop)
        return monitor

    def test_unsupported_platform_does_not_load_native_libraries(self):
        monitor = self.monitor()
        with patch.object(power.sys, "platform", "linux"), patch.object(power, "_NativePowerNotifications") as native:
            self.assertFalse(monitor.start())
            self.assertEqual(monitor.status, "unsupported")
            native.assert_not_called()

    def test_start_stop_are_idempotent_and_restart_works(self):
        instances = []

        def factory(callback):
            native = FakeNotifications(callback)
            instances.append(native)
            return native

        monitor = self.monitor()
        with patch.object(power, "_NativePowerNotifications", side_effect=factory):
            self.assertTrue(monitor.start())
            self.assertTrue(monitor.start())
            self.assertEqual(len(instances), 1)
            self.assertTrue(instances[0].polling.wait(1))
            monitor.stop()
            monitor.stop()
            self.assertEqual(monitor.status, "stopped")
            self.assertTrue(instances[0].closed)
            self.assertFalse(monitor._thread.is_alive())
            self.assertTrue(monitor.start())
            self.assertEqual(len(instances), 2)
            monitor.stop()
            self.assertTrue(instances[1].closed)

    def test_registration_failure_is_safe_and_releases_partial_resources(self):
        native = FakeNotifications(None)
        native.open = Mock(side_effect=OSError("PRIVATE_DIAGNOSTIC"))
        monitor = self.monitor()
        with patch.object(power, "_NativePowerNotifications", return_value=native):
            self.assertFalse(monitor.start())
            monitor._thread.join(1)
        self.assertTrue(native.closed)
        self.assertEqual(monitor.status, "unavailable")
        self.assertNotIn("PRIVATE_DIAGNOSTIC", monitor.error)

    def test_loading_failure_does_not_escape(self):
        monitor = self.monitor()
        with patch.object(power, "_NativePowerNotifications", side_effect=OSError("Missing library")):
            self.assertFalse(monitor.start())
        self.assertEqual(monitor.status, "unavailable")

    def test_run_loop_failure_reports_unavailable_and_closes(self):
        native = FakeNotifications(None)
        native.poll = Mock(side_effect=OSError("loop ended"))
        monitor = self.monitor()
        with patch.object(power, "_NativePowerNotifications", return_value=native):
            monitor.start()
            monitor._thread.join(1)
        self.assertEqual(monitor.status, "unavailable")
        self.assertTrue(native.closed)

    def test_acknowledges_before_callback_and_forwards_only_actual_sleep_wake(self):
        events = []
        monitor = self.monitor(lambda event, timestamp: events.append((event, timestamp)))
        monitor._native = Mock()
        monitor._native.allow.side_effect = lambda value: events.append(("ack", value))
        with patch.object(power.time, "time", return_value=123.25):
            for message in (power.CAN_SLEEP, 0xE0000290, power.WILL_SLEEP,
                            0xE0000320, power.HAS_POWERED_ON, 0xE0000210):
                monitor._notification(None, 0, message, 99)
        self.assertEqual(events, [("ack", 99), ("ack", 99), ("sleep", 123.25), ("wake", 123.25)])

    def test_callback_exception_is_contained_after_acknowledgement(self):
        callback = Mock(side_effect=RuntimeError("PRIVATE_ERROR"))
        monitor = self.monitor(callback)
        monitor._native = Mock()
        monitor._notification(None, 0, power.WILL_SLEEP, 321)
        monitor._native.allow.assert_called_once_with(321)
        self.assertIn("处理失败", monitor.error)
        self.assertNotIn("PRIVATE_ERROR", monitor.error)
        callback.side_effect = None
        monitor._notification(None, 0, power.HAS_POWERED_ON, None)
        self.assertEqual(callback.call_count, 2)

    def test_acknowledgement_failure_is_contained_and_not_reported_as_confirmed_sleep(self):
        callback = Mock()
        monitor = self.monitor(callback)
        monitor._native = Mock()
        monitor._native.allow.side_effect = OSError("ack failure")
        monitor._notification(None, 0, power.WILL_SLEEP, 321)
        callback.assert_not_called()
        self.assertIsNotNone(monitor.error)


class NativeNotificationsTests(unittest.TestCase):
    def native(self):
        # Exercise registration/cleanup ordering without loading any framework.
        native = power._NativePowerNotifications.__new__(power._NativePowerNotifications)
        native.iokit, native.cf = Mock(), Mock()
        native.port, native.notifier = ctypes.c_void_p(8), ctypes.c_uint32(9)
        native.mode, native.callback = object(), object()
        native.connection, native.source, native.loop = 0, None, None
        return native

    def test_registration_and_cleanup_release_all_handles_once(self):
        native = self.native()
        native.iokit.IORegisterForSystemPower.return_value = 3
        native.iokit.IONotificationPortGetRunLoopSource.return_value = 4
        native.cf.CFRunLoopGetCurrent.return_value = 5
        native.open()
        native.cf.CFRunLoopAddSource.assert_called_once_with(5, 4, native.mode)
        native.close()
        native.close()
        native.cf.CFRunLoopRemoveSource.assert_called_once_with(5, 4, native.mode)
        native.iokit.IODeregisterForSystemPower.assert_called_once()
        native.iokit.IOServiceClose.assert_called_once_with(3)
        native.iokit.IONotificationPortDestroy.assert_called_once()
        self.assertEqual(native.connection, 0)
        self.assertIsNone(native.port.value)

    def test_failed_registration_releases_partial_port(self):
        native = self.native()
        native.iokit.IORegisterForSystemPower.return_value = 0
        with self.assertRaises(OSError):
            native.open()
        native.close()
        native.iokit.IONotificationPortDestroy.assert_called_once()
        native.cf.CFRunLoopAddSource.assert_not_called()

    def test_ack_and_runloop_return_values_are_checked(self):
        native = self.native()
        native.connection = 3
        native.iokit.IOAllowPowerChange.return_value = 0
        native.allow(99)
        native.iokit.IOAllowPowerChange.assert_called_once_with(3, 99)
        native.iokit.IOAllowPowerChange.return_value = -1
        with self.assertRaises(OSError):
            native.allow(99)
        native.cf.CFRunLoopRunInMode.return_value = 3
        native.poll()
        native.cf.CFRunLoopRunInMode.assert_called_once_with(native.mode, 0.25, False)
        native.cf.CFRunLoopRunInMode.return_value = 1
        with self.assertRaises(OSError):
            native.poll()


if __name__ == "__main__":
    unittest.main()
