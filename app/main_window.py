from __future__ import annotations
import ctypes
import os
import uuid
from pathlib import Path
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout

from app.ui.dashboard import DashboardWidget
from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager
from app.utils.global_hotkey import GlobalHotkey


class _GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    )

    @classmethod
    def parse(cls, value: str):
        parsed = uuid.UUID(value)
        return cls(
            parsed.time_low,
            parsed.time_mid,
            parsed.time_hi_version,
            (ctypes.c_ubyte * 8).from_buffer_copy(parsed.bytes[8:]),
        )


class _RECT(ctypes.Structure):
    _fields_ = (("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long))


class _MSG(ctypes.Structure):
    _fields_ = (
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_ulong),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    )


class MainAppWindow(QMainWindow):
    DESIGN_WIDTH = 1060
    DESIGN_HEIGHT = 720
    DESIGN_ASPECT = DESIGN_WIDTH / DESIGN_HEIGHT

    def __init__(self, parent=None, settings_manager=None,
                 translation_manager: TranslationManager = None,
                 theme_manager: ThemeManager = None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        self.setWindowTitle("CodexUU")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg")))
        self._aspect_adjusting = False
        self._pending_aspect_size = None
        self._last_normal_size = QSize(self.DESIGN_WIDTH, self.DESIGN_HEIGHT)
        # The dashboard is authored and tested at this logical client size.
        # Allowing a smaller window compresses fixed-height metric/model rows
        # and makes stacked pages paint outside their visible viewport.
        self.setMinimumSize(self.DESIGN_WIDTH, self.DESIGN_HEIGHT)
        self.resize(self.DESIGN_WIDTH, self.DESIGN_HEIGHT)
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

    @classmethod
    def constrained_client_size(cls, width: int, height: int, drive: str = "width") -> QSize:
        """Return a standard-or-larger client size with the design aspect ratio."""
        width = max(cls.DESIGN_WIDTH, int(width))
        height = max(cls.DESIGN_HEIGHT, int(height))
        if drive == "height":
            width = max(cls.DESIGN_WIDTH, round(height * cls.DESIGN_ASPECT))
            height = round(width / cls.DESIGN_ASPECT)
        else:
            height = max(cls.DESIGN_HEIGHT, round(width / cls.DESIGN_ASPECT))
            width = round(height * cls.DESIGN_ASPECT)
        return QSize(width, height)

    def _normal_resize_target(self, size: QSize) -> QSize:
        previous = self._last_normal_size
        width_delta = abs(size.width() - previous.width()) / max(1, previous.width())
        height_delta = abs(size.height() - previous.height()) / max(1, previous.height())
        drive = "width" if width_delta >= height_delta else "height"
        target = self.constrained_client_size(size.width(), size.height(), drive)
        screen = self.screen()
        if screen:
            available = screen.availableGeometry().size()
            frame_width = max(0, self.frameGeometry().width() - self.width())
            frame_height = max(0, self.frameGeometry().height() - self.height())
            max_width = max(self.DESIGN_WIDTH, available.width() - frame_width)
            max_height = max(self.DESIGN_HEIGHT, available.height() - frame_height)
            if target.width() > max_width or target.height() > max_height:
                scale = min(max_width / target.width(), max_height / target.height())
                fitted_width = max(self.DESIGN_WIDTH, round(target.width() * scale))
                target = self.constrained_client_size(fitted_width, self.DESIGN_HEIGHT, "width")
        return target

    def _apply_pending_aspect_resize(self):
        target = self._pending_aspect_size
        self._pending_aspect_size = None
        if target is None or self.isMaximized() or self.isFullScreen() or self.isMinimized():
            return
        if self.size() == target:
            self._last_normal_size = QSize(target)
            return
        self._aspect_adjusting = True
        self.resize(target)
        self._aspect_adjusting = False
        self._last_normal_size = QSize(target)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self._aspect_adjusting or self.isMaximized() or self.isFullScreen() or self.isMinimized():
            return
        target = self._normal_resize_target(event.size())
        self._last_normal_size = QSize(event.size())
        if abs(target.width() - event.size().width()) <= 1 and abs(target.height() - event.size().height()) <= 1:
            self._last_normal_size = QSize(target)
            return
        self._pending_aspect_size = target
        QTimer.singleShot(0, self._apply_pending_aspect_resize)

    def nativeEvent(self, event_type, message):
        """Lock interactive Windows edge/corner resizing to the design ratio."""
        if os.name == "nt" and not self.isMaximized() and not self.isFullScreen():
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == 0x0214 and msg.lParam:  # WM_SIZING
                    rect = ctypes.cast(msg.lParam, ctypes.POINTER(_RECT)).contents
                    current = self.frameGeometry()
                    frame_width = max(0, current.width() - self.width())
                    frame_height = max(0, current.height() - self.height())
                    min_outer_width = self.DESIGN_WIDTH + frame_width
                    min_outer_height = self.DESIGN_HEIGHT + frame_height
                    outer_aspect = min_outer_width / max(1, min_outer_height)
                    width = max(min_outer_width, rect.right - rect.left)
                    height = max(min_outer_height, rect.bottom - rect.top)
                    horizontal_edges = (1, 2)
                    vertical_edges = (3, 6)
                    if msg.wParam in horizontal_edges:
                        drive = "width"
                    elif msg.wParam in vertical_edges:
                        drive = "height"
                    else:
                        dw = abs(width - current.width()) / max(1, current.width())
                        dh = abs(height - current.height()) / max(1, current.height())
                        drive = "width" if dw >= dh else "height"
                    if drive == "width":
                        height = max(min_outer_height, round(width / outer_aspect))
                        width = round(height * outer_aspect)
                    else:
                        width = max(min_outer_width, round(height * outer_aspect))
                        height = round(width / outer_aspect)
                    if msg.wParam in (1, 4, 7):
                        rect.left = rect.right - width
                    else:
                        rect.right = rect.left + width
                    if msg.wParam in (3, 4, 5):
                        rect.top = rect.bottom - height
                    else:
                        rect.bottom = rect.top + height
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _apply_manager_theme(self):
        if self.theme_manager:
            self.setStyleSheet(self.theme_manager.get_stylesheet())
        QTimer.singleShot(0, self._apply_windows_chrome)

    def toggle_visibility(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_and_activate()

    def show_and_activate(self):
        """Restore a hidden/minimized lightweight window and request foreground focus."""
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.setWindowState(
            (self.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()
        if os.name == "nt":
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        QTimer.singleShot(80, self._apply_windows_chrome)

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
        """Use the Shell taskbar API without turning the caption into a tool window."""
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
            style = int(get_style(hwnd, -16))
            # Explicitly retain caption controls even after upgrading from an
            # older WS_EX_TOOLWINDOW session.
            standard_controls = 0x00080000 | 0x00020000 | 0x00010000 | 0x00040000
            target_style = style | standard_controls
            exstyle = int(get_style(hwnd, -20))
            tool_window = 0x00000080
            app_window = 0x00040000
            target_exstyle = exstyle & ~tool_window
            target_exstyle = (
                target_exstyle & ~app_window
                if self._lightweight_mode
                else target_exstyle | app_window
            )
            if target_style != style:
                set_style(hwnd, -16, target_style)
            if target_exstyle != exstyle:
                set_style(hwnd, -20, target_exstyle)
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0004 | 0x0020,
            )
            self._set_taskbar_tab(hwnd, visible=not self._lightweight_mode)
        except Exception:
            pass

    @staticmethod
    def _set_taskbar_tab(hwnd: int, visible: bool) -> bool:
        """Call ITaskbarList AddTab/DeleteTab through its stable COM vtable."""
        if os.name != "nt":
            return False
        ole32 = ctypes.windll.ole32
        initialized = False
        taskbar = ctypes.c_void_p()
        try:
            init_result = int(ole32.CoInitialize(None))
            initialized = init_result in (0, 1)
            clsid = _GUID.parse("56FDF344-FD6D-11D0-958A-006097C9A090")
            iid = _GUID.parse("56FDF342-FD6D-11D0-958A-006097C9A090")
            ole32.CoCreateInstance.argtypes = (
                ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint32,
                ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
            )
            ole32.CoCreateInstance.restype = ctypes.c_long
            result = ole32.CoCreateInstance(
                ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(taskbar),
            )
            if result < 0 or not taskbar.value:
                return False
            vtable = ctypes.cast(taskbar, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            no_arg = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
            with_hwnd = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
            hr_init = no_arg(vtable[3])
            add_tab = with_hwnd(vtable[4])
            delete_tab = with_hwnd(vtable[5])
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
            if hr_init(taskbar) < 0:
                return False
            result = add_tab(taskbar, hwnd) if visible else delete_tab(taskbar, hwnd)
            return result >= 0
        finally:
            if taskbar.value:
                try:
                    release(taskbar)
                except Exception:
                    pass
            if initialized:
                ole32.CoUninitialize()

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

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        QTimer.singleShot(120, self._apply_windows_chrome)
