from __future__ import annotations
import ctypes
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout

from app.ui.dashboard import DashboardWidget


class MainAppWindow(QMainWindow):
    def __init__(self, parent=None, settings_manager=None, 
                 translation_manager=None, theme_manager=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        
        self.setWindowTitle("codexU")
        self.setMinimumSize(960, 680)
        self.resize(1060, 740)

        self.setStyleSheet("QMainWindow { background: #12122a; }")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.dashboard = DashboardWidget(translation_manager=self.translation_manager)
        layout.addWidget(self.dashboard)

        QShortcut(QKeySequence("Ctrl+U"), self).activated.connect(self.toggle_visibility)
        self._apply_dark_titlebar()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _apply_dark_titlebar(self):
        try:
            hwnd = int(self.winId())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()
