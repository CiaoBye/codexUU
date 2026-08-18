from __future__ import annotations
import ctypes
import os
import uuid
from pathlib import Path
from PySide6.QtCore import QEvent, QSize, Qt, QTimer
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


class _POINT(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class _MINMAXINFO(ctypes.Structure):
    _fields_ = (
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    )


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
    DEFAULT_DPI = 96

    WM_GETMINMAXINFO = 0x0024
    WM_SIZING = 0x0214
    WM_ENTERSIZEMOVE = 0x0231
    WM_EXITSIZEMOVE = 0x0232
    WM_DPICHANGED = 0x02E0

    WMSZ_LEFT = 1
    WMSZ_RIGHT = 2
    WMSZ_TOP = 3
    WMSZ_TOPLEFT = 4
    WMSZ_TOPRIGHT = 5
    WMSZ_BOTTOM = 6
    WMSZ_BOTTOMLEFT = 7
    WMSZ_BOTTOMRIGHT = 8

    def __init__(self, parent=None, settings_manager=None,
                 translation_manager: TranslationManager = None,
                 theme_manager: ThemeManager = None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        self.setWindowTitle("CodexUU")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg")))
        self._windows_sizing = False
        self._sizing_start_rect = None
        self._last_normal_size = QSize(self.DESIGN_WIDTH, self.DESIGN_HEIGHT)
        self._native_dpi = self.DEFAULT_DPI
        self._native_event_error = None
        self._resize_settle_timer = QTimer(self)
        self._resize_settle_timer.setSingleShot(True)
        self._resize_settle_timer.timeout.connect(self._finish_resize_interaction)
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

    @staticmethod
    def logical_to_native(value: int, dpi: int = DEFAULT_DPI) -> int:
        """Convert a Qt logical pixel value to a Windows physical pixel value."""
        return max(1, round(int(value) * max(1, int(dpi)) / MainAppWindow.DEFAULT_DPI))

    @classmethod
    def native_minimum_outer_size(cls, dpi: int, margins) -> tuple[int, int]:
        """Return the minimum native tracking size for the logical client canvas."""
        left, top, right, bottom = (max(0, int(value)) for value in margins)
        return (
            cls.logical_to_native(cls.DESIGN_WIDTH, dpi) + left + right,
            cls.logical_to_native(cls.DESIGN_HEIGHT, dpi) + top + bottom,
        )

    @staticmethod
    def constrained_outer_rect(
        left: int,
        top: int,
        right: int,
        bottom: int,
        edge: int,
        client_aspect: float,
        min_width: int,
        min_height: int,
        frame_width: int = 0,
        frame_height: int = 0,
        start_width: int | None = None,
        start_height: int | None = None,
    ) -> tuple[int, int, int, int]:
        """Constrain a Windows sizing rectangle without moving its fixed edges."""
        requested_width = max(1, int(right) - int(left))
        requested_height = max(1, int(bottom) - int(top))
        min_width = max(1, int(min_width))
        min_height = max(1, int(min_height))
        client_aspect = max(0.01, float(client_aspect))
        frame_width = max(0, int(frame_width))
        frame_height = max(0, int(frame_height))

        horizontal_edges = {MainAppWindow.WMSZ_LEFT, MainAppWindow.WMSZ_RIGHT}
        vertical_edges = {MainAppWindow.WMSZ_TOP, MainAppWindow.WMSZ_BOTTOM}
        if edge in horizontal_edges:
            drive = "width"
        elif edge in vertical_edges:
            drive = "height"
        else:
            reference_width = max(1, int(start_width or requested_width))
            reference_height = max(1, int(start_height or requested_height))
            width_delta = abs(requested_width - reference_width) / reference_width
            height_delta = abs(requested_height - reference_height) / reference_height
            drive = "width" if width_delta >= height_delta else "height"

        if drive == "width":
            width = max(min_width, requested_width)
            client_width = max(1, width - frame_width)
            client_height = round(client_width / client_aspect)
            height = client_height + frame_height
            if height < min_height:
                height = min_height
                client_height = max(1, height - frame_height)
                client_width = round(client_height * client_aspect)
                width = max(width, client_width + frame_width)
        else:
            height = max(min_height, requested_height)
            client_height = max(1, height - frame_height)
            client_width = round(client_height * client_aspect)
            width = client_width + frame_width
            if width < min_width:
                width = min_width
                client_width = max(1, width - frame_width)
                client_height = round(client_width / client_aspect)
                height = max(height, client_height + frame_height)

        if edge in {MainAppWindow.WMSZ_LEFT, MainAppWindow.WMSZ_TOPLEFT, MainAppWindow.WMSZ_BOTTOMLEFT}:
            left = int(right) - width
        else:
            right = int(left) + width
        if edge in {MainAppWindow.WMSZ_TOP, MainAppWindow.WMSZ_TOPLEFT, MainAppWindow.WMSZ_TOPRIGHT}:
            top = int(bottom) - height
        else:
            bottom = int(top) + height
        return int(left), int(top), int(right), int(bottom)

    def _window_dpi(self, hwnd=None) -> int:
        if os.name != "nt":
            return self.DEFAULT_DPI
        try:
            hwnd = int(hwnd or self.winId())
            get_dpi = ctypes.windll.user32.GetDpiForWindow
            get_dpi.argtypes = (ctypes.c_void_p,)
            get_dpi.restype = ctypes.c_uint
            dpi = int(get_dpi(hwnd))
            if dpi > 0:
                return dpi
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        return self.DEFAULT_DPI

    def _native_window_rect(self, hwnd=None):
        if os.name != "nt":
            frame = self.frameGeometry()
            return frame.left(), frame.top(), frame.right() + 1, frame.bottom() + 1
        try:
            hwnd = int(hwnd or self.winId())
            rect = _RECT()
            get_rect = ctypes.windll.user32.GetWindowRect
            get_rect.argtypes = (ctypes.c_void_p, ctypes.POINTER(_RECT))
            get_rect.restype = ctypes.c_int
            if get_rect(hwnd, ctypes.byref(rect)):
                return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        frame = self.frameGeometry()
        return frame.left(), frame.top(), frame.right() + 1, frame.bottom() + 1

    def _native_frame_margins(self, hwnd=None):
        """Read the real non-client margins instead of estimating title-bar size."""
        if os.name == "nt":
            try:
                hwnd = int(hwnd or self.winId())
                window = _RECT()
                client = _RECT()
                origin = _POINT(0, 0)
                user32 = ctypes.windll.user32
                get_window_rect = user32.GetWindowRect
                get_window_rect.argtypes = (ctypes.c_void_p, ctypes.POINTER(_RECT))
                get_window_rect.restype = ctypes.c_int
                get_client_rect = user32.GetClientRect
                get_client_rect.argtypes = (ctypes.c_void_p, ctypes.POINTER(_RECT))
                get_client_rect.restype = ctypes.c_int
                client_to_screen = user32.ClientToScreen
                client_to_screen.argtypes = (ctypes.c_void_p, ctypes.POINTER(_POINT))
                client_to_screen.restype = ctypes.c_int
                if (
                    get_window_rect(hwnd, ctypes.byref(window))
                    and get_client_rect(hwnd, ctypes.byref(client))
                    and client_to_screen(hwnd, ctypes.byref(origin))
                ):
                    client_width = max(0, int(client.right) - int(client.left))
                    client_height = max(0, int(client.bottom) - int(client.top))
                    return (
                        max(0, int(origin.x) - int(window.left)),
                        max(0, int(origin.y) - int(window.top)),
                        max(0, int(window.right) - int(origin.x) - client_width),
                        max(0, int(window.bottom) - int(origin.y) - client_height),
                    )
            except (AttributeError, OSError, TypeError, ValueError):
                pass

        dpi = self._window_dpi(hwnd)
        frame = self.frameGeometry()
        return (
            max(0, self.logical_to_native(frame.width() - self.width(), dpi) // 2),
            max(0, self.logical_to_native(frame.height() - self.height(), dpi) // 2),
            max(0, self.logical_to_native(frame.width() - self.width(), dpi) // 2),
            max(0, self.logical_to_native(frame.height() - self.height(), dpi) // 2),
        )

    def resize_normal_client(self, width: int, height: int, drive: str = "width"):
        """Apply an intentional programmatic normal-window resize."""
        if self.isMaximized() or self.isFullScreen() or self.isMinimized():
            return
        target = self.constrained_client_size(width, height, drive)
        self.resize(target)

    def _mark_resize_interaction(self):
        dashboard = getattr(self, "dashboard", None)
        if dashboard is not None:
            dashboard.set_resizing(True)
        self._resize_settle_timer.start(160)

    def _finish_resize_interaction(self):
        dashboard = getattr(self, "dashboard", None)
        if dashboard is not None:
            dashboard.set_resizing(False)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self.isMinimized():
            return
        self._mark_resize_interaction()
        # The Windows sizing loop is the only authority for interactive
        # aspect locking. A resize event is a layout notification only; a
        # second Qt resize here creates a visible feedback loop on Windows.
        if not self._windows_sizing and not self.isMaximized() and not self.isFullScreen():
            self._last_normal_size = QSize(event.size())

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            # Maximize/restore can resize the whole dashboard without going
            # through the normal drag path. Stop value and tab animations for
            # that transition as well.
            self._mark_resize_interaction()

    def nativeEvent(self, event_type, message):
        """Apply Windows-native tracking constraints without fighting Qt layout."""
        if os.name == "nt":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == self.WM_GETMINMAXINFO and msg.lParam:
                    info = ctypes.cast(int(msg.lParam), ctypes.POINTER(_MINMAXINFO)).contents
                    dpi = self._window_dpi()
                    self._native_dpi = dpi
                    margins = self._native_frame_margins()
                    min_width, min_height = self.native_minimum_outer_size(dpi, margins)
                    info.ptMinTrackSize.x = max(int(info.ptMinTrackSize.x), min_width)
                    info.ptMinTrackSize.y = max(int(info.ptMinTrackSize.y), min_height)
                    return True, 0
                if msg.message == self.WM_ENTERSIZEMOVE:
                    self._windows_sizing = True
                    self._sizing_start_rect = self._native_window_rect()
                    self._mark_resize_interaction()
                    return False, 0
                if msg.message == self.WM_EXITSIZEMOVE:
                    self._windows_sizing = False
                    self._sizing_start_rect = None
                    self._last_normal_size = QSize(self.size())
                    self._mark_resize_interaction()
                    return False, 0
                if msg.message == self.WM_DPICHANGED:
                    dpi = int(msg.wParam) & 0xFFFF
                    if dpi > 0:
                        self._native_dpi = dpi
                    self._mark_resize_interaction()
                    # Qt 6 is Per-Monitor-DPI aware and applies the suggested
                    # rectangle after this hook. Do not call resize() here.
                    return False, 0
                if msg.message == self.WM_SIZING and msg.lParam and not self.isMaximized() and not self.isFullScreen():
                    self._windows_sizing = True
                    self._mark_resize_interaction()
                    rect = ctypes.cast(msg.lParam, ctypes.POINTER(_RECT)).contents
                    dpi = self._window_dpi()
                    self._native_dpi = dpi
                    margins = self._native_frame_margins()
                    min_width, min_height = self.native_minimum_outer_size(dpi, margins)
                    left, top, right, bottom = self.constrained_outer_rect(
                        rect.left,
                        rect.top,
                        rect.right,
                        rect.bottom,
                        int(msg.wParam),
                        self.DESIGN_ASPECT,
                        min_width,
                        min_height,
                        frame_width=margins[0] + margins[2],
                        frame_height=margins[1] + margins[3],
                        start_width=(self._sizing_start_rect[2] - self._sizing_start_rect[0]) if self._sizing_start_rect else None,
                        start_height=(self._sizing_start_rect[3] - self._sizing_start_rect[1]) if self._sizing_start_rect else None,
                    )
                    rect.left, rect.top, rect.right, rect.bottom = left, top, right, bottom
                    return False, 0
            except Exception as exc:
                self._native_event_error = f"{type(exc).__name__}: {exc}"
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
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                fg_hwnd = user32.GetForegroundWindow()
                attached = False
                if fg_hwnd and fg_hwnd != hwnd:
                    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                    cur_tid = kernel32.GetCurrentThreadId()
                    if fg_tid != cur_tid and fg_tid != 0:
                        attached = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
                try:
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.SwitchToThisWindow(hwnd, True)
                finally:
                    if attached:
                        user32.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                pass

    def show_without_activation(self):
        """Show a native window for background validation without taking focus."""
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
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
