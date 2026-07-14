from __future__ import annotations
import ctypes
import os
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout

from app.ui.dashboard import DashboardWidget
from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager
from app.utils.global_hotkey import GlobalHotkey


class MainAppWindow(QMainWindow):
    def __init__(self, parent=None, settings_manager=None,
                 translation_manager: TranslationManager = None,
                 theme_manager: ThemeManager = None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        self.setWindowTitle("CodexUU")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg")))
        self.setMinimumSize(1060, 720)
        self.resize(1180, 800)
        self.setObjectName("mainWindow")

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.dashboard = DashboardWidget(
            settings_manager=settings_manager,
            translation_manager=translation_manager,
            theme_manager=theme_manager,
        )
        layout.addWidget(self.dashboard)
        self.global_hotkey = GlobalHotkey(QApplication.instance(), self, self)
        self.global_hotkey.activated.connect(self.toggle_visibility)
        self.hotkey_registered = False
        self._applied_shortcut = ""
        self._always_on_top = False
        self._lightweight_mode = False
        if self.theme_manager:
            self.theme_manager.add_listener(self._apply_manager_theme)
        if self.settings_manager:
            self.settings_manager.add_listener(self._apply_window_settings)
        self._apply_window_settings()
        QTimer.singleShot(0, self._apply_windows_chrome)

    def _apply_manager_theme(self):
        if self.theme_manager:
            self.setStyleSheet(self.theme_manager.get_stylesheet())
        QTimer.singleShot(0, self._apply_windows_chrome)

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _apply_window_settings(self):
        if not self.settings_manager:
            return
        always_on_top, _ = self.settings_manager.get_window_preferences()
        lightweight_mode = self.settings_manager.get_lightweight_mode()
        if always_on_top != self._always_on_top or lightweight_mode != self._lightweight_mode:
            was_visible = self.isVisible()
            flags = self.windowFlags()
            flags &= ~Qt.WindowType.WindowType_Mask
            # Keep a normal top-level window so Windows supplies the standard
            # minimize / maximize / close buttons.  Taskbar visibility is an
            # extended style concern and must not turn the window into Qt.Tool.
            flags |= Qt.WindowType.Window
            flags = flags | Qt.WindowType.WindowStaysOnTopHint if always_on_top else flags & ~Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self._always_on_top = always_on_top
            self._lightweight_mode = lightweight_mode
            if was_visible:
                self.show()
        self._apply_windows_chrome()
        shortcut = self.settings_manager.get_shortcut()
        if shortcut != self._applied_shortcut:
            self.try_register_shortcut(shortcut)

    def try_register_shortcut(self, shortcut):
        previous = self._applied_shortcut
        self.hotkey_registered = self.global_hotkey.register(shortcut)
        if self.hotkey_registered:
            self._applied_shortcut = shortcut
            return True
        if previous and previous != shortcut:
            self.hotkey_registered = self.global_hotkey.register(previous)
        return False

    def _handle_close_request(self):
        behavior = self.settings_manager.get_window_preferences()[1] if self.settings_manager else "tray"
        if behavior == "quit":
            QApplication.instance().quit()
        elif behavior == "minimize":
            self.showMinimized()
        else:
            self.hide()

    def _apply_windows_chrome(self):
        self._apply_taskbar_visibility()
        self._apply_dark_titlebar()

    def _apply_taskbar_visibility(self):
        """Hide only the taskbar entry in lightweight mode, never the native caption."""
        if os.name != "nt":
            return
        try:
            hwnd = int(self.winId())
            get_style = ctypes.windll.user32.GetWindowLongW
            set_style = ctypes.windll.user32.SetWindowLongW
            get_style.argtypes = (ctypes.c_void_p, ctypes.c_int)
            get_style.restype = ctypes.c_long
            set_style.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_long)
            set_style.restype = ctypes.c_long
            exstyle = int(get_style(hwnd, -20))  # GWL_EXSTYLE
            tool_window = 0x00000080  # WS_EX_TOOLWINDOW: no taskbar button
            target = exstyle | tool_window if self._lightweight_mode else exstyle & ~tool_window
            if target != exstyle:
                set_style(hwnd, -20, target)
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0,
                    0x0001 | 0x0002 | 0x0004 | 0x0020,  # frame changed, no move/size/z-order
                )
        except Exception:
            # A normal taskbar button is safer than changing the native window
            # frame when a Windows API is unavailable.
            pass

    def _apply_dark_titlebar(self):
        try:
            hwnd = int(self.winId())
            dark = bool(self.theme_manager and self.theme_manager.get_effective_theme() == "dark")
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1 if dark else 0)), ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self._handle_close_request()
