from __future__ import annotations
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QFrame, QVBoxLayout, QLabel,
)

from app.data.models import MultiRuntimeUsageSnapshot, format_tokens

FONT = "Microsoft YaHei"


class TrayManager(QObject):
    show_main_window = Signal()
    show_settings = Signal()
    quit_app = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = MultiRuntimeUsageSnapshot()
        self._setup_tray()

    def _setup_tray(self):
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#60a5fa"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, 18, 18, 4, 4)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont(FONT, 9, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "U")
        painter.end()
        icon = QIcon(pixmap)

        self.tray_icon = QSystemTrayIcon(icon)
        self.tray_icon.setToolTip("codexU")

        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1e1e3a; color: #e0e0e0; border: 1px solid #333;"
            "border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 6px 16px; border-radius: 4px; }"
            "QMenu::item:selected { background: rgba(96,165,250,0.4); }"
            "QMenu::separator { height: 1px; background: #333; margin: 4px 8px; }"
        )

        show_action = QAction("\u6253\u5f00\u4e3b\u7a97\u53e3", menu)
        show_action.triggered.connect(self.show_main_window.emit)
        menu.addAction(show_action)

        settings_action = QAction("\u8bbe\u7f6e", menu)
        settings_action.triggered.connect(self.show_settings.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("\u9000\u51fa", menu)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(
            lambda reason: self.show_main_window.emit()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray_icon.show()

    def update_data(self, data):
        self.data = data
        total = data.codex.tokens.today_total + data.claude_code.tokens.today_total
        self.tray_icon.setToolTip(f"codexU | \u4eca\u65e5: {format_tokens(total)}")
