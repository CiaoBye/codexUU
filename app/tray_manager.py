from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QRectF, Signal, QObject
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.data.models import MultiRuntimeUsageSnapshot, format_tokens
from app.desktop_status import DesktopStatusPanel


class TrayManager(QObject):
    show_main_window = Signal()
    show_settings = Signal()
    quit_app = Signal()
    status_icon_changed = Signal(object)

    def __init__(self, settings_manager=None, theme_manager=None, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        self.data = MultiRuntimeUsageSnapshot()
        self._icon_key = None
        self._quota_alerts: set[tuple[str, str, str]] = set()
        self.desktop_panel = DesktopStatusPanel()
        self.desktop_panel.show_main.connect(self._open_main)
        self.desktop_panel.position_changed.connect(self._save_desktop_status_position)
        self.desktop_panel.style_change_requested.connect(self._set_desktop_status_style)
        self.desktop_panel.size_change_requested.connect(self._set_desktop_status_size)
        self.desktop_panel.mode_change_requested.connect(self._set_quota_display)
        self.desktop_panel.hide_requested.connect(lambda: self._set_desktop_status_enabled(False))
        self._setup_tray()
        if self.settings_manager:
            self.settings_manager.add_listener(self._on_settings_changed)
        if self.theme_manager:
            self.theme_manager.add_listener(self._on_theme_changed)
            self.desktop_panel.set_theme(self.theme_manager.get_effective_theme())
        self._sync_desktop_status()

    def _setup_tray(self):
        icon_path = Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg"
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)))
        self.tray_icon.setToolTip("CodexUU")
        menu = QMenu()
        show_action = QAction("打开主窗口", menu)
        show_action.triggered.connect(self._open_main)
        menu.addAction(show_action)
        self.desktop_action = QAction("桌面悬浮状态", menu)
        self.desktop_action.setCheckable(True)
        self.desktop_action.toggled.connect(self._set_desktop_status_enabled)
        menu.addAction(self.desktop_action)
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
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._open_main()

    def _open_main(self):
        self.show_main_window.emit()

    def _open_settings(self):
        self.show_settings.emit()

    def _on_settings_changed(self):
        self._refresh_status_icon()
        self._sync_desktop_status()

    def _on_theme_changed(self):
        if self.theme_manager:
            self.desktop_panel.set_theme(self.theme_manager.get_effective_theme())

    def _set_desktop_status_enabled(self, enabled):
        if not self.settings_manager:
            return
        self.settings_manager.set_desktop_status_enabled(enabled)
        self.settings_manager.save()

    def _save_desktop_status_position(self, position):
        if self.settings_manager:
            self.settings_manager.set_desktop_status_position(position.x(), position.y())
            self.settings_manager.save()

    def _set_desktop_status_style(self, style):
        if self.settings_manager:
            self.settings_manager.set_desktop_status_style(style)
            self.settings_manager.save()

    def _set_desktop_status_size(self, size):
        if self.settings_manager:
            self.settings_manager.set_desktop_status_size(size)
            self.settings_manager.save()

    def _set_quota_display(self, mode):
        if self.settings_manager:
            self.settings_manager.set_quota_display(mode)
            self.settings_manager.save()

    def _sync_desktop_status(self):
        enabled = False
        position = None
        style = "orb"
        size = "medium"
        if self.settings_manager:
            enabled, position = self.settings_manager.get_desktop_status_preferences()
            style = self.settings_manager.get_desktop_status_style()
            size = self.settings_manager.get_desktop_status_size()
        self.desktop_panel.set_style(style)
        self.desktop_panel.set_display_size(size)
        self.desktop_panel.set_display_mode(
            self.settings_manager.get_quota_display() if self.settings_manager else "remaining"
        )
        if self.theme_manager:
            self.desktop_panel.set_theme(self.theme_manager.get_effective_theme())
        if hasattr(self, "desktop_action"):
            blocked = self.desktop_action.blockSignals(True)
            self.desktop_action.setChecked(enabled)
            self.desktop_action.blockSignals(blocked)
        if not enabled:
            self.desktop_panel.hide()
            return
        if not self.desktop_panel.isVisible():
            self._place_desktop_status(position)
            self.desktop_panel.show()
        else:
            # A style may change the circle diameter; clamp the persisted
            # position again so it never overflows the current screen.
            self._place_desktop_status(position or (self.desktop_panel.x(), self.desktop_panel.y()))
        self.desktop_panel.raise_()

    def _place_desktop_status(self, position):
        point = QPoint(*position) if position is not None else QCursor.pos()
        screen = QApplication.screenAt(point) or QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        if position is None:
            x = available.right() - self.desktop_panel.width() - 18
            y = available.top() + 56
        else:
            x, y = position
        x = min(max(available.left() + 8, x), available.right() - self.desktop_panel.width() - 8)
        y = min(max(available.top() + 8, y), available.bottom() - self.desktop_panel.height() - 8)
        self.desktop_panel.move(x, y)

    def update_data(self, data):
        self.data = data
        runtime = self.settings_manager.get_active_runtime() if self.settings_manager else "codex"
        snapshot = data.claude_code if runtime == "claudeCode" else data.codex
        self.desktop_panel.update_snapshot(runtime, snapshot)
        self._refresh_status_icon()
        self._notify_quota_alerts()

    def _notify_quota_alerts(self):
        threshold = self.settings_manager.get_quota_alert_threshold() if self.settings_manager else 0
        if threshold <= 0:
            self._quota_alerts.clear()
            return
        if not self.tray_icon.supportsMessages():
            return
        active: set[tuple[str, str, str]] = set()
        for runtime, snapshot in (("codex", self.data.codex), ("claudeCode", self.data.claude_code)):
            quota_name, quota = ("7d", snapshot.quota_7d) if snapshot.quota_7d else ("5h", snapshot.quota_5h)
            if quota is None or quota.remaining_pct > threshold:
                continue
            reset = quota.reset_time.isoformat() if quota.reset_time else "unknown-reset"
            key = (runtime, quota_name, reset)
            active.add(key)
            if key in self._quota_alerts:
                continue
            runtime_name = "Claude Code" if runtime == "claudeCode" else "Codex"
            self.tray_icon.showMessage(
                "CodexUU 额度提醒",
                f"{runtime_name} {quota_name} 剩余 {quota.remaining_pct:.0f}%（提醒阈值 {threshold}%）。",
                QSystemTrayIcon.MessageIcon.Warning,
                10000,
            )
            self._quota_alerts.add(key)
        self._quota_alerts.intersection_update(active)

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
            f"今日 {format_tokens(snapshot.tokens.today.total)}\n单击打开主窗口"
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
            painter.setPen(QPen(color, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            start = 270 if mode == "used" else 90
            painter.drawArc(bounds, start * 16, -int(360 * 16 * value / 100))
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
