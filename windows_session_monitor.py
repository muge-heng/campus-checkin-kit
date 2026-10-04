import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget


WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOGON = 0x0005
WTS_SESSION_UNLOCK = 0x0008
NOTIFY_FOR_THIS_SESSION = 0


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _Msg(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


class WindowsSessionMonitor(QWidget):
    """Reports a Windows unlock event, with recent user activity as a fallback."""

    session_restored = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._registered = False
        self._previous_idle_ms = self._idle_milliseconds()
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.winId()
        self._register_for_session_events()

    def _register_for_session_events(self) -> None:
        try:
            registered = ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                wintypes.HWND(int(self.winId())),
                NOTIFY_FOR_THIS_SESSION,
            )
            self._registered = bool(registered)
        except Exception:
            self._registered = False

    def closeEvent(self, event) -> None:
        if self._registered:
            try:
                ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(int(self.winId())))
            except Exception:
                pass
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        try:
            native_message = ctypes.cast(int(message), ctypes.POINTER(_Msg)).contents
            if native_message.message == WM_WTSSESSION_CHANGE and native_message.wParam in {
                WTS_SESSION_LOGON,
                WTS_SESSION_UNLOCK,
            }:
                self.session_restored.emit("Windows 解锁后")
        except Exception:
            pass
        return False, 0

    def poll_for_activity_resume(self) -> None:
        """Cover systems where session messages are not delivered to the hidden window."""
        idle_ms = self._idle_milliseconds()
        if self._previous_idle_ms >= 60_000 and idle_ms <= 15_000:
            self.session_restored.emit("回到桌面后")
        self._previous_idle_ms = idle_ms

    @staticmethod
    def _idle_milliseconds() -> int:
        try:
            info = _LastInputInfo()
            info.cbSize = ctypes.sizeof(_LastInputInfo)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return 0
            return max(0, ctypes.windll.kernel32.GetTickCount() - info.dwTime)
        except Exception:
            return 0
