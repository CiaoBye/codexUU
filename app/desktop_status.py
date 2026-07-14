from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QLineF, QPoint, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import (
    QActionGroup,
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QMenu, QWidget

from app.data.models import format_tokens
from app.utils.statistics_timezone import get_statistics_timezone


class DesktopStatusPanel(QWidget):
    """可拖动桌面额度窗；单击打开/切换口径，双击最小化主窗。"""

    show_main = Signal()
    minimize_main = Signal()
    position_changed = Signal(QPoint)
    style_change_requested = Signal(str)
    size_change_requested = Signal(str)
    mode_change_requested = Signal(str)
    hide_requested = Signal()

    _BASE_GEOMETRY = {
        "orb": (176, 176),
        "halo": (188, 188),
        "mini": (116, 116),
        "capsule": (300, 104),
        "tracks": (280, 140),
    }
    _SIZE_FACTORS = {"small": 0.86, "medium": 1.0, "large": 1.18}
    _STYLE_LABELS = {
        "orb": "信息圆盘",
        "halo": "双环仪表",
        "mini": "极简圆环",
        "capsule": "状态胶囊",
        "tracks": "双轨卡片",
    }
    _SIZE_LABELS = {"small": "小", "medium": "中", "large": "大"}
    _CLICK_DELAY_MS = 220

    def __init__(self, parent=None):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self.setObjectName("desktopStatusPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start: QPoint | None = None
        self._style = "orb"
        self._size = "medium"
        self._theme = "dark"
        self._runtime = "Codex"
        self._today = "0"
        self._q5 = None
        self._q7 = None
        self._display_mode = "remaining"
        self._press_position: QPoint | None = None
        self._dragged = False
        self._pressed = False
        self._pending_click_center = False
        self._suppress_release = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._commit_single_click)
        self._apply_geometry()

    def set_style(self, style: str):
        self._style = style if style in self._BASE_GEOMETRY else "orb"
        self._apply_geometry()

    def set_display_size(self, size: str):
        self._size = size if size in self._SIZE_FACTORS else "medium"
        self._apply_geometry()

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self.update()

    def set_display_mode(self, mode: str):
        self._display_mode = mode if mode in ("remaining", "used") else "remaining"
        self._update_tooltip()
        self.update()

    def _apply_geometry(self):
        base_width, base_height = self._BASE_GEOMETRY[self._style]
        factor = self._SIZE_FACTORS[self._size]
        self.setFixedSize(round(base_width * factor), round(base_height * factor))
        self.updateGeometry()
        self.update()

    def update_snapshot(self, runtime: str, snapshot):
        self._runtime = "Claude Code" if runtime == "claudeCode" else "Codex"
        self._today = format_tokens(snapshot.tokens.today.total)
        self._q5 = snapshot.quota_5h
        self._q7 = snapshot.quota_7d
        self._update_tooltip()
        self.update()

    def _update_tooltip(self):
        available = [("5H", self._q5), ("7D", self._q7)]
        available = [(label, quota) for label, quota in available if quota is not None]
        mode_label = "已用" if self._display_mode == "used" else "剩余"
        if not available:
            tip = f"{self._runtime}\n暂无可验证额度窗口\n单击打开主窗口 · 双击最小化主窗口 · 右键调整样式"
        else:
            lines = [self._runtime]
            for label, quota in available:
                value = quota.used_pct if self._display_mode == "used" else quota.remaining_pct
                lines.append(f"{label} {mode_label} {value:.0f}% · {self._format_reset(quota) or '重置时间未知'}")
            lines.extend((f"今日 {self._today}", "单击中心切换口径 · 单击其他区域打开 · 双击最小化主窗口"))
            tip = "\n".join(lines)
        self.setToolTip(tip)

    @staticmethod
    def _format_reset(quota) -> str:
        if quota is None or quota.reset_time is None:
            return ""
        local_time: datetime = quota.reset_time.astimezone(get_statistics_timezone().tzinfo())
        return f"重置 {local_time.strftime('%m/%d %H:%M')}"

    def _scaled_font(self, family: str, pixels: float, weight=QFont.Weight.Normal) -> QFont:
        font = QFont(family)
        base_width, _ = self._BASE_GEOMETRY[self._style]
        font.setPixelSize(max(8, round(pixels * self.width() / base_width)))
        font.setWeight(weight)
        return font

    @staticmethod
    def _draw_centered(painter: QPainter, rect: QRectF, text: str, font: QFont, color: QColor):
        painter.setFont(font)
        painter.setPen(color)
        metrics = QFontMetrics(font)
        available = max(0, round(rect.width()) - 6)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, metrics.elidedText(text, Qt.TextElideMode.ElideRight, available))

    @staticmethod
    def _draw_text(painter: QPainter, rect: QRectF, text: str, font: QFont, color: QColor, alignment):
        painter.setFont(font)
        painter.setPen(color)
        metrics = QFontMetrics(font)
        available = max(0, round(rect.width()) - 4)
        painter.drawText(rect, alignment, metrics.elidedText(text, Qt.TextElideMode.ElideRight, available))

    def _quota_value(self, quota):
        if quota is None:
            return None
        value = quota.used_pct if self._display_mode == "used" else quota.remaining_pct
        return max(0.0, min(100.0, float(value)))

    def _mode_label(self):
        return "已用" if self._display_mode == "used" else "剩余"

    def _arc(self, value, degrees=360):
        # Both modes share the bottom origin: used grows along the left side,
        # remaining grows along the right side.
        direction = -1 if self._display_mode == "used" else 1
        return 270 * 16, direction * int(degrees * 16 * value / 100)

    def _draw_ring(self, painter, rect, quota, color, track, width):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(track, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        value = self._quota_value(quota)
        if value is not None:
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, *self._arc(value))
        return value

    def _ring_layout(self, bounds, primary, secondary):
        """Return outer 7D purple first, inner 5H blue second."""
        if self._q5 is not None and self._q7 is not None:
            return (
                (bounds.adjusted(bounds.width() * .10, bounds.height() * .10, -bounds.width() * .10, -bounds.height() * .10), self._q7, primary, "7D"),
                (bounds.adjusted(bounds.width() * .22, bounds.height() * .22, -bounds.width() * .22, -bounds.height() * .22), self._q5, secondary, "5H"),
            )
        quota = self._q7 or self._q5
        label = "7D" if self._q7 is not None else "5H"
        color = primary if self._q7 is not None else secondary
        return ((bounds.adjusted(bounds.width() * .14, bounds.height() * .14, -bounds.width() * .14, -bounds.height() * .14), quota, color, label),) if quota else ()

    @staticmethod
    def _draw_track(painter, rect, value, color, track, width=7):
        painter.setPen(QPen(track, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QLineF(rect.left(), rect.center().y(), rect.right(), rect.center().y()))
        if value is None:
            return
        end = rect.left() + rect.width() * max(0.0, min(100.0, value)) / 100
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QLineF(rect.left(), rect.center().y(), end, rect.center().y()))

    def _paint_capsule(self, painter, surface, edge, track, primary, secondary, text, muted):
        panel = QRectF(5, 5, self.width() - 10, self.height() - 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50 if self._theme == "dark" else 24))
        painter.drawRoundedRect(panel.translated(0, 2), panel.height() / 2, panel.height() / 2)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(surface)
        painter.drawRoundedRect(panel, panel.height() / 2, panel.height() / 2)
        ring_bounds = QRectF(12, 12, self.height() - 24, self.height() - 24)
        rings = self._ring_layout(ring_bounds, primary, secondary)
        ring_width = max(5, self.height() * 0.052)
        for ring, quota, color, _label in rings:
            self._draw_ring(painter, ring, quota, color, track, ring_width)
        active = self._q7 or self._q5
        active_value = self._quota_value(active)
        self._draw_centered(
            painter, ring_bounds.adjusted(12, 17, -12, -17),
            "--" if active_value is None else f"{active_value:.0f}%",
            self._scaled_font("Segoe UI Variable Display", 18, QFont.Weight.Bold), text,
        )

        content_left = ring_bounds.right() + 13
        content_width = panel.right() - content_left - 14
        self._draw_text(
            painter, QRectF(content_left, 13, content_width - 34, 25), f"今日 {self._today}",
            self._scaled_font("Microsoft YaHei", 14, QFont.Weight.Bold), text,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._draw_text(
            painter, QRectF(panel.right() - 50, 15, 34, 18), self._mode_label(),
            self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), primary,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        available = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        available = [item for item in available if item[1] is not None]
        row_y = 43 if len(available) == 2 else 57
        row_step = 23
        for index, (label, quota, color) in enumerate(available):
            y = row_y + index * row_step
            value = self._quota_value(quota)
            reset = self._format_reset(quota).replace("重置 ", "") or "--"
            self._draw_text(
                painter, QRectF(content_left, y, 74, 18), f"{label} {value:.0f}%",
                self._scaled_font("Segoe UI Variable", 9, QFont.Weight.DemiBold), color,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            self._draw_text(
                painter, QRectF(content_left + 76, y, content_width - 76, 18), reset,
                self._scaled_font("Microsoft YaHei", 8), muted,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )

    def _paint_tracks(self, painter, surface, edge, track, primary, secondary, text, muted):
        panel = QRectF(5, 5, self.width() - 10, self.height() - 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50 if self._theme == "dark" else 24))
        painter.drawRoundedRect(panel.translated(0, 2), 18, 18)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(surface)
        painter.drawRoundedRect(panel, 18, 18)
        divider_x = panel.left() + 88
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(divider_x, panel.top() + 16, divider_x, panel.bottom() - 16))
        self._draw_text(painter, QRectF(panel.left() + 14, 35, 65, 18), "今日", self._scaled_font("Microsoft YaHei", 9), muted, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._draw_text(painter, QRectF(panel.left() + 14, 55, 68, 31), self._today, self._scaled_font("Segoe UI Variable Display", 19, QFont.Weight.Bold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._draw_text(painter, QRectF(panel.left() + 14, 15, 65, 17), self._runtime, self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._draw_text(painter, QRectF(panel.left() + 14, 91, 65, 17), self._mode_label(), self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), primary, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        rows = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        rows = [item for item in rows if item[1] is not None]
        if not rows:
            self._draw_centered(painter, QRectF(divider_x + 8, 47, panel.right() - divider_x - 16, 34), "暂无可验证额度", self._scaled_font("Microsoft YaHei", 9), muted)
        else:
            content_left = divider_x + 17
            content_width = panel.right() - content_left - 16
            start_y = 32 if len(rows) == 2 else 53
            step = 49
            for index, (label, quota, color) in enumerate(rows):
                y = start_y + index * step
                value = self._quota_value(quota)
                self._draw_text(painter, QRectF(content_left, y - 11, content_width, 18), f"{label}  {value:.0f}%", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._draw_track(painter, QRectF(content_left, y + 11, content_width, 8), value, color, track, max(6, self.height() * 0.05))
                reset = self._format_reset(quota).replace("重置 ", "") or "--"
                self._draw_text(painter, QRectF(content_left, y + 20, content_width, 16), reset, self._scaled_font("Microsoft YaHei", 8), muted, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pressed:
            painter.translate(self.width() / 2, self.height() / 2)
            painter.scale(.985, .985)
            painter.translate(-self.width() / 2, -self.height() / 2)
        dark = self._theme == "dark"
        surface = QColor("#151d2b") if dark else QColor("#ffffff")
        edge = QColor("#354258") if dark else QColor("#d6e0ee")
        track = QColor("#2c3749") if dark else QColor("#e7ebf2")
        primary = QColor("#8b72ff") if dark else QColor("#705cf2")
        secondary = QColor("#44a2ff") if dark else QColor("#3188e8")
        text = QColor("#f5f7fb") if dark else QColor("#18243a")
        muted = QColor("#9cabc1") if dark else QColor("#667995")

        if self._style == "capsule":
            self._paint_capsule(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return
        if self._style == "tracks":
            self._paint_tracks(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return

        diameter = min(self.width(), self.height())
        shadow = QRectF(7, 9, diameter - 14, diameter - 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 55 if dark else 28))
        painter.drawEllipse(shadow.translated(0, 2))

        bounds = QRectF(6, 6, diameter - 12, diameter - 12)
        painter.setBrush(surface)
        painter.setPen(QPen(edge, max(1.0, diameter / 180)))
        painter.drawEllipse(bounds.adjusted(2, 2, -2, -2))

        available = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        available = [item for item in available if item[1] is not None]
        active_label, active_quota, active_color = available[-1] if available else ("--", None, primary)
        active_value = self._quota_value(active_quota)

        if self._style == "orb":
            rings = self._ring_layout(bounds, primary, secondary)
            ring_width = diameter * (0.045 if len(rings) == 2 else 0.06)
            for ring, quota, color, _label in rings:
                self._draw_ring(painter, ring, quota, color, track, ring_width)
            if len(rings) == 2:
                q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
                self._draw_centered(painter, QRectF(diameter*.25, diameter*.25, diameter*.50, diameter*.13), f"5H  {q5:.0f}%", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), secondary)
                self._draw_centered(painter, QRectF(diameter*.25, diameter*.43, diameter*.50, diameter*.13), f"7D  {q7:.0f}%", self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), primary)
                reset5 = self._format_reset(self._q5).replace("重置 ", "") or "--"
                reset7 = self._format_reset(self._q7).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter*.20, diameter*.36, diameter*.60, diameter*.09), reset5, self._scaled_font("Microsoft YaHei", 7), muted)
                self._draw_centered(painter, QRectF(diameter*.17, diameter*.56, diameter*.66, diameter*.10), reset7, self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), muted)
                self._draw_centered(painter, QRectF(diameter*.26, diameter*.70, diameter*.48, diameter*.09), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), text)
            else:
                value_text = "--" if active_value is None else f"{active_value:.0f}%"
                self._draw_centered(painter, QRectF(diameter*.22, diameter*.28, diameter*.56, diameter*.13), f"{active_label} · {self._mode_label()}", self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), active_color)
                self._draw_centered(painter, QRectF(diameter*.15, diameter*.40, diameter*.70, diameter*.20), value_text, self._scaled_font("Segoe UI Variable Display", 27, QFont.Weight.Bold), text)
                reset = self._format_reset(active_quota).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter*.18, diameter*.61, diameter*.64, diameter*.11), reset, self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), muted)
                self._draw_centered(painter, QRectF(diameter*.27, diameter*.73, diameter*.46, diameter*.08), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 7), muted)
        elif self._style == "halo":
            rings = self._ring_layout(bounds, primary, secondary)
            ring_width = diameter * 0.052
            for ring, quota, color, _label in rings:
                self._draw_ring(painter, ring, quota, color, track, ring_width)
            if len(rings) == 2:
                q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
                self._draw_centered(painter, QRectF(diameter*.27, diameter*.29, diameter*.46, diameter*.14), f"5H  {q5:.0f}%", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), secondary)
                self._draw_centered(painter, QRectF(diameter*.27, diameter*.44, diameter*.46, diameter*.14), f"7D  {q7:.0f}%", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), primary)
                reset5 = self._format_reset(self._q5).replace("重置 ", "") or "--"
                reset7 = self._format_reset(self._q7).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter*.18, diameter*.61, diameter*.64, diameter*.10), f"{reset5} · {reset7}", self._scaled_font("Microsoft YaHei", 7, QFont.Weight.DemiBold), muted)
                self._draw_centered(painter, QRectF(diameter*.31, diameter*.72, diameter*.38, diameter*.09), self._mode_label(), self._scaled_font("Microsoft YaHei", 8), muted)
            else:
                value_text = "--" if active_value is None else f"{active_value:.0f}%"
                self._draw_centered(painter, QRectF(diameter*.28, diameter*.29, diameter*.44, diameter*.12), f"{active_label} · {self._mode_label()}", self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), active_color)
                self._draw_centered(painter, QRectF(diameter*.20, diameter*.40, diameter*.60, diameter*.20), value_text, self._scaled_font("Segoe UI Variable Display", 24, QFont.Weight.Bold), text)
                reset = self._format_reset(active_quota).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter*.20, diameter*.61, diameter*.60, diameter*.12), reset, self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), muted)
        else:
            rings = self._ring_layout(bounds, primary, secondary)
            ring_width = diameter * (0.047 if len(rings) == 2 else 0.065)
            for ring, quota, color, _label in rings:
                self._draw_ring(painter, ring, quota, color, track, ring_width)
            if len(rings) == 2:
                q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
                self._draw_centered(painter, QRectF(0, diameter*.29, diameter, diameter*.16), f"5H {q5:.0f}%", self._scaled_font("Segoe UI Variable", 8, QFont.Weight.Bold), secondary)
                self._draw_centered(painter, QRectF(0, diameter*.46, diameter, diameter*.18), f"7D {q7:.0f}%", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), primary)
            else:
                self._draw_centered(painter, QRectF(0, diameter*.29, diameter, diameter*.16), f"{active_label} · {self._mode_label()}", self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), active_color)
                value_text = "--" if active_value is None else f"{active_value:.0f}%"
                self._draw_centered(painter, QRectF(0, diameter*.44, diameter, diameter*.22), value_text, self._scaled_font("Segoe UI Variable Display", 21, QFont.Weight.Bold), text)
                reset = self._format_reset(active_quota).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter*.19, diameter*.67, diameter*.62, diameter*.10), reset, self._scaled_font("Microsoft YaHei", 7), muted)
        painter.end()

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = QMenu(self)
        style_menu = menu.addMenu("显示样式")
        style_group = QActionGroup(style_menu)
        style_group.setExclusive(True)
        for key, label in self._STYLE_LABELS.items():
            action = style_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == self._style)
            action.triggered.connect(lambda _checked=False, value=key: self.style_change_requested.emit(value))
            style_group.addAction(action)
        size_menu = menu.addMenu("悬浮窗大小")
        size_group = QActionGroup(size_menu)
        size_group.setExclusive(True)
        for key, label in self._SIZE_LABELS.items():
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == self._size)
            action.triggered.connect(lambda _checked=False, value=key: self.size_change_requested.emit(value))
            size_group.addAction(action)
        menu.addSeparator()
        menu.addAction("打开主窗口", self.show_main.emit)
        menu.addAction("隐藏悬浮窗", self.hide_requested.emit)
        menu.exec(event.globalPos())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_position = event.position().toPoint()
            self._dragged = False
            self._pressed = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if self._press_position is not None and (event.position().toPoint() - self._press_position).manhattanLength() > 4:
                self._dragged = True
                if self._pressed:
                    self._pressed = False
                    self.update()
            self.move(event.globalPosition().toPoint() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._suppress_release:
            self._suppress_release = False
            self._drag_start = None
            self._press_position = None
            self._pressed = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            click_position = event.position().toPoint()
            should_toggle = not self._dragged and self._mode_hit_test(click_position)
            self._drag_start = None
            self._press_position = None
            self._pressed = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
            if self._dragged:
                self.position_changed.emit(self.pos())
            else:
                self._pending_click_center = should_toggle
                self._click_timer.start(self._CLICK_DELAY_MS)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self._suppress_release = True
            self._pressed = False
            self.update()
            self.minimize_main.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _commit_single_click(self):
        if self._pending_click_center:
            next_mode = "used" if self._display_mode == "remaining" else "remaining"
            self.set_display_mode(next_mode)
            self.mode_change_requested.emit(next_mode)
        else:
            self.show_main.emit()

    def _mode_hit_test(self, position: QPoint) -> bool:
        if self._style == "capsule":
            center = QPoint(self.height() // 2, self.height() // 2)
            radius = self.height() * 0.31
            delta = position - center
            return delta.x() ** 2 + delta.y() ** 2 <= radius ** 2
        if self._style == "tracks":
            zone = self.rect().adjusted(
                round(self.width() * 0.28), round(self.height() * 0.25),
                -round(self.width() * 0.28), -round(self.height() * 0.25),
            )
            return zone.contains(position)
        center = self.rect().center()
        delta = position - center
        radius = min(self.width(), self.height()) * 0.30
        return delta.x() ** 2 + delta.y() ** 2 <= radius ** 2
