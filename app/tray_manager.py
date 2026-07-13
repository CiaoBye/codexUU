from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal, QObject
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.data.models import MultiRuntimeUsageSnapshot, format_tokens


def _quota_text(quota, prefix):
    return f"{prefix} {quota.remaining_pct:.0f}%" if quota else f"{prefix} --"


class RuntimeQuickCard(QFrame):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName("trayRuntimeCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(5)
        header = QHBoxLayout()
        self.name = QLabel(name)
        self.name.setObjectName("projectName")
        header.addWidget(self.name)
        header.addStretch()
        self.today = QLabel("0")
        self.today.setObjectName("projectToken")
        header.addWidget(self.today)
        layout.addLayout(header)
        self.quota = QLabel("5h -- · 7d --")
        self.quota.setObjectName("caption")
        layout.addWidget(self.quota)

    def set_snapshot(self, snapshot):
        self.today.setText(f"今日 {format_tokens(snapshot.tokens.today.total)}")
        self.quota.setText(
            f"{_quota_text(snapshot.quota_5h, '5h')}  ·  {_quota_text(snapshot.quota_7d, '7d')}"
        )


class TrayQuickPanel(QWidget):
    show_main = Signal()
    show_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("trayQuickPanel")
        self.setFixedWidth(330)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("trayPanel")
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(9)
        header = QHBoxLayout()
        logo = QLabel()
        logo_path = Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg"
        logo.setPixmap(QPixmap(str(logo_path)).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(logo)
        title = QLabel("CodexUU")
        title.setObjectName("brandName")
        header.addWidget(title)
        header.addStretch()
        self.updated = QLabel("本机快速状态")
        self.updated.setObjectName("caption")
        header.addWidget(self.updated)
        layout.addLayout(header)
        self.codex = RuntimeQuickCard("Codex")
        self.claude = RuntimeQuickCard("Claude Code")
        layout.addWidget(self.codex)
        layout.addWidget(self.claude)
        actions = QHBoxLayout()
        open_button = QPushButton("打开主窗口")
        open_button.setObjectName("primaryButton")
        open_button.clicked.connect(self.show_main.emit)
        actions.addWidget(open_button)
        settings_button = QPushButton("设置")
        settings_button.setObjectName("iconButton")
        settings_button.clicked.connect(self.show_settings.emit)
        actions.addWidget(settings_button)
        layout.addLayout(actions)
        root.addWidget(shell)

    def update_data(self, data):
        self.codex.set_snapshot(data.codex)
        self.claude.set_snapshot(data.claude_code)


class TrayManager(QObject):
    show_main_window = Signal()
    show_settings = Signal()
    quit_app = Signal()
    status_icon_changed = Signal(object)

    def __init__(self, settings_manager=None, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.data = MultiRuntimeUsageSnapshot()
        self._icon_key = None
        self.panel = TrayQuickPanel()
        self.panel.show_main.connect(self._open_main)
        self.panel.show_settings.connect(self._open_settings)
        self._setup_tray()
        if self.settings_manager:
            self.settings_manager.add_listener(self._refresh_status_icon)

    def _setup_tray(self):
        icon_path = Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg"
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)))
        self.tray_icon.setToolTip("CodexUU")
        menu = QMenu()
        show_action = QAction("打开主窗口", menu)
        show_action.triggered.connect(self._open_main)
        menu.addAction(show_action)
        quick_action = QAction("快速状态", menu)
        quick_action.triggered.connect(self.toggle_panel)
        menu.addAction(quick_action)
        settings_action = QAction("设置", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._activated)
        self.tray_icon.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_panel()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._open_main()

    def toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
            return
        self.panel.adjustSize()
        tray_rect = self.tray_icon.geometry()
        screen = QApplication.screenAt(tray_rect.center()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        x = min(max(available.left() + 8, tray_rect.center().x() - self.panel.width() // 2), available.right() - self.panel.width() - 8)
        y = tray_rect.top() - self.panel.height() - 10
        if y < available.top():
            y = tray_rect.bottom() + 10
        self.panel.move(x, y)
        self.panel.show()
        self.panel.raise_()

    def _open_main(self):
        self.panel.hide()
        self.show_main_window.emit()

    def _open_settings(self):
        self.panel.hide()
        self.show_settings.emit()

    def update_data(self, data):
        self.data = data
        self.panel.update_data(data)
        self._refresh_status_icon()

    def _refresh_status_icon(self):
        runtime = self.settings_manager.get_active_runtime() if self.settings_manager else "codex"
        snapshot = self.data.claude_code if runtime == "claudeCode" else self.data.codex
        mode = self.settings_manager.get_quota_display() if self.settings_manager else "remaining"
        quota = snapshot.quota_7d or snapshot.quota_5h
        value = None
        if quota is not None:
            value = quota.used_pct if mode == "used" else quota.remaining_pct
        icon_key = (runtime, mode, None if value is None else round(value))
        if icon_key != self._icon_key:
            icon = self._status_icon(value, mode)
            self.tray_icon.setIcon(icon)
            self.status_icon_changed.emit(icon)
            self._icon_key = icon_key
        runtime_name = "Claude Code" if runtime == "claudeCode" else "Codex"
        quota_name = "7d" if snapshot.quota_7d else "5h"
        quota_text = "--" if value is None else f"{value:.0f}%"
        mode_text = "已用" if mode == "used" else "剩余"
        self.tray_icon.setToolTip(
            f"CodexUU\n{runtime_name} · {quota_name} {mode_text} {quota_text}\n"
            f"今日 {format_tokens(snapshot.tokens.today.total)}\n单击查看快速状态"
        )

    @staticmethod
    def _status_icon(value, mode):
        """Windows 通知区只允许图标；用动态额度环表达状态，避免常驻文本。"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(8, 8, 48, 48)
        painter.setPen(QPen(QColor("#d8deea"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(bounds, 0, 360 * 16)
        if value is not None:
            value = max(0.0, min(100.0, float(value)))
            color = QColor("#3296f3") if mode == "used" else QColor("#8668f2")
            direction = 1 if mode == "used" else -1
            painter.setPen(QPen(color, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(bounds, 90 * 16, int(direction * 360 * 16 * value / 100))
            text = f"{value:.0f}"
        else:
            text = "U"
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f8fafc"))
        painter.drawEllipse(bounds.adjusted(7, 7, -7, -7))
        painter.setPen(QColor("#25324a"))
        painter.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.Bold))
        painter.drawText(QRectF(12, 15, 40, 32), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return QIcon(pixmap)
