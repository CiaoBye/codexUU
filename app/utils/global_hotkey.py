from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0xC0DE


def parse_shortcut(value: str):
    parts = [part.strip().lower() for part in str(value or "").split("+") if part.strip()]
    modifiers = 0
    key = None
    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        elif part in ("meta", "win", "windows"):
            modifiers |= MOD_WIN
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x70 + int(part[1:]) - 1
    return (modifiers, key) if modifiers and key else None


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
                return True, 0
        except (TypeError, ValueError, OSError):
            pass
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()

    def __init__(self, app, window, parent=None):
        super().__init__(parent)
        self.app = app
        self.window = window
        self.registered = False
        self.filter = _NativeFilter(self.activated.emit)
        if os.name == "nt":
            app.installNativeEventFilter(self.filter)

    def register(self, shortcut: str) -> bool:
        self.unregister()
        parsed = parse_shortcut(shortcut)
        if os.name != "nt" or parsed is None:
            return False
        modifiers, key = parsed
        self.registered = bool(ctypes.windll.user32.RegisterHotKey(
            int(self.window.winId()), HOTKEY_ID, modifiers | MOD_NOREPEAT, key,
        ))
        return self.registered

    def unregister(self):
        if os.name == "nt" and self.registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.window.winId()), HOTKEY_ID)
        self.registered = False
