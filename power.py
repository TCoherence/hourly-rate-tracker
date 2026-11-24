"""Observe macOS system sleep/wake without changing power settings or VPN state.

Uses the standard library and public IOKit/CoreFoundation APIs. Acknowledgement
rules: https://developer.apple.com/library/archive/qa/qa1340/_index.html
Message constants: apple-oss-distributions/xnu, iokit/IOKit/IOMessage.h.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time


CAN_SLEEP = 0xE0000270
WILL_SLEEP = 0xE0000280
HAS_POWERED_ON = 0xE0000300
CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32,
                           ctypes.c_uint32, ctypes.c_void_p)


class _NativePowerNotifications:
    """All registration, run-loop work and cleanup happen on one thread."""

    def __init__(self, callback):
        self.iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        pointer, uint = ctypes.c_void_p, ctypes.c_uint32
        signatures = (
            (self.iokit.IORegisterForSystemPower,
             [pointer, ctypes.POINTER(pointer), CALLBACK, ctypes.POINTER(uint)], uint),
            (self.iokit.IONotificationPortGetRunLoopSource, [pointer], pointer),
            (self.iokit.IOAllowPowerChange, [uint, ctypes.c_ssize_t], ctypes.c_int32),
            (self.iokit.IODeregisterForSystemPower, [ctypes.POINTER(uint)], ctypes.c_int32),
            (self.iokit.IOServiceClose, [uint], ctypes.c_int32),
            (self.iokit.IONotificationPortDestroy, [pointer], None),
            (self.cf.CFRunLoopGetCurrent, [], pointer),
            (self.cf.CFRunLoopAddSource, [pointer, pointer, pointer], None),
            (self.cf.CFRunLoopRemoveSource, [pointer, pointer, pointer], None),
            (self.cf.CFRunLoopRunInMode, [pointer, ctypes.c_double, ctypes.c_bool], ctypes.c_int32),
        )
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result
        self.mode = pointer.in_dll(self.cf, "kCFRunLoopDefaultMode")
        self.port, self.notifier = pointer(), uint()
        self.connection, self.loop, self.source = 0, None, None
        # Keep the C function pointer alive until deregistration completes.
        self.callback = CALLBACK(callback)

    def open(self):
        self.connection = self.iokit.IORegisterForSystemPower(
            None, ctypes.byref(self.port), self.callback, ctypes.byref(self.notifier))
        if not self.connection:
            raise OSError("System power notifications unavailable")
        self.source = self.iokit.IONotificationPortGetRunLoopSource(self.port)
        if not self.source:
            raise OSError("System power notification source unavailable")
        self.loop = self.cf.CFRunLoopGetCurrent()
        self.cf.CFRunLoopAddSource(self.loop, self.source, self.mode)

    def allow(self, notification):
        if self.iokit.IOAllowPowerChange(self.connection, notification or 0):
            raise OSError("System power acknowledgement failed")

    def poll(self):
        # A bounded run permits clean shutdown without cross-thread pointer races.
        result = self.cf.CFRunLoopRunInMode(self.mode, 0.25, False)
        if result == 1:  # kCFRunLoopRunFinished: the registered source disappeared.
            raise OSError("System power notification source ended")

    def close(self):
        if self.loop and self.source:
            self.cf.CFRunLoopRemoveSource(self.loop, self.source, self.mode)
            self.loop, self.source = None, None
        if self.notifier.value:
            self.iokit.IODeregisterForSystemPower(ctypes.byref(self.notifier))
            self.notifier.value = 0
        if self.connection:
            self.iokit.IOServiceClose(self.connection)
            self.connection = 0
        if self.port.value:
            self.iokit.IONotificationPortDestroy(self.port)
            self.port.value = None


class PowerMonitor:
    """Deliver ``callback('sleep' | 'wake', unix_timestamp)`` on a worker thread.

    Callbacks should be short. Sleep permission is acknowledged before calling
    application code, including when that code raises. No sleep is ever vetoed.
    Unsupported systems and unavailable notifications leave VPN sampling intact.
    """

    def __init__(self, callback):
        self.callback = callback
        self.status, self.error = "stopped", None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._native = None

    def _notification(self, refcon, service, message, argument):
        # Never let an exception cross the C callback boundary. Capture the wall
        # time before acknowledgement, since the OS may suspend us immediately.
        try:
            timestamp = time.time()
            if message in (CAN_SLEEP, WILL_SLEEP):
                self._native.allow(argument)
            if message == WILL_SLEEP:
                self.callback("sleep", timestamp)
            elif message == HAS_POWERED_ON:
                self.callback("wake", timestamp)
        except BaseException:
            self.error = "系统睡眠事件处理失败；未确认时段仍按未知处理"

    def _run(self):
        try:
            self._native = _NativePowerNotifications(self._notification)
            self._native.open()
            if self._stop.is_set():
                return
            self.status = "running"
            self._ready.set()
            while not self._stop.is_set():
                self._native.poll()
        except Exception:
            self.status, self.error = "unavailable", "无法监听系统睡眠；采样缺口仍按未知处理"
        finally:
            try:
                if self._native is not None:
                    self._native.close()
            except Exception:
                self.status, self.error = "unavailable", "系统睡眠监听停止异常"
            self._native = None
            if self._stop.is_set() and self.status != "unavailable":
                self.status = "stopped"
            self._ready.set()

    def start(self):
        if self._thread and self._thread.is_alive():
            return self.status == "running"
        if sys.platform != "darwin":
            self.status, self.error = "unsupported", "系统睡眠监听仅支持 macOS"
            return False
        self._stop.clear()
        self._ready.clear()
        self.status, self.error = "starting", None
        self._thread = threading.Thread(target=self._run, name="local-sleep-observer", daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            self._stop.set()
            self.status, self.error = "unavailable", "系统睡眠监听启动超时"
            return False
        return self.status == "running"

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        if self._thread and self._thread.is_alive():
            self.status, self.error = "unavailable", "系统睡眠监听尚未停止"
