"""Read display sleep state through public CoreGraphics APIs; never alter displays."""
from __future__ import annotations

import ctypes
import sys


class DisplayMonitor:
    """Query every online display conservatively; None means unknown.

    Polling establishes only the state at the instant of the query. An empty,
    changing or unavailable display list never means that screens are asleep.
    """
    def __init__(self, platform=None, library=None):
        self.platform = platform or sys.platform
        self.library = library
        self.error = None

    def _load(self):
        if self.library is None:
            self.library = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
            self.library.CGGetOnlineDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
            self.library.CGGetOnlineDisplayList.restype = ctypes.c_int32
            self.library.CGDisplayIsAsleep.argtypes = [ctypes.c_uint32]
            self.library.CGDisplayIsAsleep.restype = ctypes.c_uint32
        return self.library

    def read(self):
        if self.platform != 'darwin':
            self.error = '屏幕状态检测目前仅支持 macOS。'
            return None
        try:
            lib = self._load()
            count = ctypes.c_uint32()
            if lib.CGGetOnlineDisplayList(0, None, ctypes.byref(count)) != 0 or not 0 < count.value <= 64:
                raise ValueError('display list unavailable')
            displays = (ctypes.c_uint32 * count.value)()
            actual = ctypes.c_uint32()
            if lib.CGGetOnlineDisplayList(count.value, displays, ctypes.byref(actual)) != 0 or not 0 < actual.value <= count.value:
                raise ValueError('display list changed')
            result = all(bool(lib.CGDisplayIsAsleep(displays[i])) for i in range(actual.value))
            self.error = None
            return result
        except (OSError, ValueError, AttributeError):
            self.error = '屏幕状态暂时无法确认，未知时段不会触发提醒。'
            return None
