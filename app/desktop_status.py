from __future__ import annotations

from datetime import datetime
import math

from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, Signal, QTimer
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
    scale_change_requested = Signal(float)
    hide_requested = Signal()

    _BASE_GEOMETRY = {
        "orb": (250, 250),
        "halo": (250, 250),
        "mini": (250, 250),
        "capsule": (330, 150),
        "tracks": (330, 150),
    }
    _SIZE_FACTORS = {"small": 0.20, "medium": 1.0, "large": 1.18}
    _MIN_SCALE = 0.20
    _MAX_SCALE = 3.0
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
        self._display_scale = self._SIZE_FACTORS[self._size]
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
        self._display_scale = self._SIZE_FACTORS[self._size]
        self._apply_geometry()

    def set_display_scale(self, scale: float):
        try:
            value = float(scale)
        except (TypeError, ValueError):
            value = self._SIZE_FACTORS["medium"]
        self._display_scale = max(self._MIN_SCALE, min(self._MAX_SCALE, value))
        matched = next((key for key, factor in self._SIZE_FACTORS.items() if abs(factor - self._display_scale) < 0.001), None)
        self._size = matched or "custom"
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
        factor = self._display_scale
        self.setFixedSize(round(base_width * factor), round(base_height * factor))
        self.updateGeometry()
        self.update()

    def _layout_scales(self) -> tuple[float, float]:
        """Map the style's fixed design canvas to the current size preset."""
        base_width, base_height = self._BASE_GEOMETRY[self._style]
        return self.width() / base_width, self.height() / base_height

    def _layout_size(self) -> tuple[float, float]:
        """Return the unscaled design-canvas size used by all paint layouts."""
        return self._BASE_GEOMETRY[self._style]

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

    @staticmethod
    def _short_reset(label: str, quota) -> str:
        if quota is None or quota.reset_time is None:
            return "--"
        local_time: datetime = quota.reset_time.astimezone(get_statistics_timezone().tzinfo())
        return local_time.strftime("%H:%M" if label == "5H" else "%m/%d %H:%M")

    def _scaled_font(self, family: str, pixels: float, weight=QFont.Weight.Normal) -> QFont:
        font = QFont(family)
        # Paint methods use a base-size canvas and paintEvent applies the size
        # preset transform.  Keep auxiliary information at a 9 px physical
        # minimum where space allows. Below 55% use strict uniform scaling so
        # even the smallest 20% canvas keeps its original proportions.
        scale = min(self._layout_scales())
        minimum_design_pixels = math.ceil(9 / scale) if scale >= .55 else 1
        font.setPixelSize(max(round(pixels), minimum_design_pixels))
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

    def _draw_panel(self, painter, surface, edge, radius=18):
        width, height = self._layout_size()
        panel = QRectF(7, 7, width - 14, height - 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 56 if self._theme == "dark" else 25))
        painter.drawRoundedRect(panel.translated(0, 3), radius, radius)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(surface)
        painter.drawRoundedRect(panel, radius, radius)
        return panel

    def _draw_circle_panel(self, painter, surface, edge):
        """Draw the complete circular surface used by every ring-only form."""
        width, height = self._layout_size()
        diameter = min(width, height) - 14
        circle = QRectF((width - diameter) / 2, (height - diameter) / 2, diameter, diameter)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 56 if self._theme == "dark" else 25))
        painter.drawEllipse(circle.translated(0, 3))
        painter.setPen(QPen(edge, 1))
        painter.setBrush(surface)
        painter.drawEllipse(circle)
        return circle

    @staticmethod
    def _draw_tick_ring(painter, rect, color, count=40, length=5):
        """Draw the inactive tick track; progress is overlaid separately."""
        painter.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        center = rect.center()
        outer_radius = rect.width() / 2
        for index in range(count):
            angle = math.radians(-90 + 360 * index / count)
            tick_length = length * (1.65 if index % 10 == 0 else 1)
            outer = QPointF(
                center.x() + math.cos(angle) * outer_radius,
                center.y() - math.sin(angle) * outer_radius,
            )
            inner = QPointF(
                center.x() + math.cos(angle) * (outer_radius - tick_length),
                center.y() - math.sin(angle) * (outer_radius - tick_length),
            )
            painter.drawLine(QLineF(inner, outer))

    def _draw_tick_progress(self, painter, rect, value, color, count=40, length=5):
        """Color only the active ticks, using the same bottom-origin direction as rings."""
        if value is None:
            return
        painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        center = rect.center()
        outer_radius = rect.width() / 2
        active_count = max(0, min(count, round(count * value / 100)))
        direction = -1 if self._display_mode == "used" else 1
        for index in range(active_count):
            angle = math.radians(-90 + direction * 360 * index / count)
            tick_length = length * (1.65 if index % 10 == 0 else 1)
            outer = QPointF(
                center.x() + math.cos(angle) * outer_radius,
                center.y() - math.sin(angle) * outer_radius,
            )
            inner = QPointF(
                center.x() + math.cos(angle) * (outer_radius - tick_length),
                center.y() - math.sin(angle) * (outer_radius - tick_length),
            )
            painter.drawLine(QLineF(inner, outer))

    def _draw_reset_stamp(self, painter, rect, label, quota, font, color):
        """Keep 7D's date and time legible inside compact capsule layouts."""
        parts = self._short_reset(label, quota).split()
        if len(parts) == 2:
            self._draw_centered(painter, QRectF(rect.left(), rect.top(), rect.width(), rect.height() / 2), parts[0], font, color)
            self._draw_centered(painter, QRectF(rect.left(), rect.center().y(), rect.width(), rect.height() / 2), parts[1], font, color)
            return
        self._draw_centered(painter, rect, parts[0] if parts else "--", font, color)

    def _draw_badge(self, painter, rect, value, text, muted, edge):
        fill = QColor("#202b3e") if self._theme == "dark" else QColor("#f5f7fb")
        painter.setPen(QPen(edge, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 6, 6)
        self._draw_centered(painter, rect, value, self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), text if value != "--" else muted)

    def _draw_tone_badge(self, painter, rect, value, color, edge):
        fill = QColor(color)
        fill.setAlpha(34 if self._theme == "dark" else 20)
        border = QColor(color)
        border.setAlpha(105 if self._theme == "dark" else 70)
        painter.setPen(QPen(border if border.isValid() else edge, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 6, 6)
        self._draw_centered(painter, rect, value, self._scaled_font("Segoe UI Variable", 8, QFont.Weight.Bold), color)

    def _draw_rings(self, painter, bounds, primary, secondary, track, width):
        rings = self._ring_layout(bounds, primary, secondary)
        for ring, quota, color, _label in rings:
            self._draw_ring(painter, ring, quota, color, track, width)
        return rings

    def _available_quotas(self, secondary, primary):
        return [item for item in (("5H", self._q5, secondary), ("7D", self._q7, primary)) if item[1] is not None]

    def _paint_orb(self, painter, surface, edge, track, primary, secondary, text, muted):
        """信息圆盘 A：双额度左右分栏，单额度居中。"""
        panel = self._draw_panel(painter, surface, edge, 18)
        available = self._available_quotas(secondary, primary)
        if len(available) == 2:
            ring_bounds = QRectF(panel.left() + 10, panel.top() + 23, 166, 166)
            self._draw_rings(painter, ring_bounds, primary, secondary, track, 8)
            info_left = ring_bounds.right() + 5
            for index, (label, quota, color) in enumerate(available):
                y = panel.top() + 29 + index * 79
                value = self._quota_value(quota)
                self._draw_text(painter, QRectF(info_left, y, 70, 21), label, self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._draw_text(painter, QRectF(info_left, y + 19, 76, 31), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 22, QFont.Weight.Bold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._draw_badge(painter, QRectF(info_left, y + 51, 76, 22), self._short_reset(label, quota), text, muted, edge)
            self._draw_text(painter, QRectF(panel.left() + 16, panel.bottom() - 34, 145, 23), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 11, QFont.Weight.DemiBold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        elif available:
            label, quota, color = available[0]
            ring_bounds = QRectF(panel.center().x() - 92, panel.top() + 13, 184, 184)
            self._draw_rings(painter, ring_bounds, primary, secondary, track, 10)
            value = self._quota_value(quota)
            self._draw_centered(painter, QRectF(panel.center().x() - 55, panel.top() + 59, 110, 22), label, self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), color)
            self._draw_centered(painter, QRectF(panel.center().x() - 70, panel.top() + 80, 140, 46), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 31, QFont.Weight.Bold), text)
            self._draw_badge(painter, QRectF(panel.center().x() - 50, panel.top() + 132, 100, 23), self._short_reset(label, quota), text, muted, edge)
            self._draw_text(painter, QRectF(panel.left() + 16, panel.bottom() - 34, 150, 23), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 11, QFont.Weight.DemiBold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self._draw_centered(painter, panel, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)

    def _paint_halo(self, painter, surface, edge, track, primary, secondary, text, muted):
        """双环仪表 A：纵向仪表、图例与今日用量。"""
        panel = self._draw_panel(painter, surface, edge, 18)
        available = self._available_quotas(secondary, primary)
        ring_bounds = QRectF(panel.center().x() - 100, panel.top() + 10, 200, 200)
        rings = self._draw_rings(painter, ring_bounds, primary, secondary, track, 9)
        if len(rings) == 2:
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            self._draw_centered(painter, QRectF(panel.center().x() - 65, panel.top() + 61, 130, 21), "5H", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(panel.center().x() - 70, panel.top() + 81, 140, 32), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(panel.center().x() - 65, panel.top() + 116, 130, 21), "7D", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(panel.center().x() - 70, panel.top() + 136, 140, 32), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), primary)
        elif available:
            label, quota, color = available[0]
            value = self._quota_value(quota)
            self._draw_centered(painter, QRectF(panel.center().x() - 65, panel.top() + 72, 130, 23), label, self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), color)
            self._draw_centered(painter, QRectF(panel.center().x() - 75, panel.top() + 98, 150, 48), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 32, QFont.Weight.Bold), color)
        else:
            self._draw_centered(painter, ring_bounds, "暂无额度", self._scaled_font("Microsoft YaHei", 11), muted)
        divider_y = panel.bottom() - 51
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(panel.left() + 24, divider_y, panel.right() - 24, divider_y))
        if available:
            reset_text = "   ".join(f"{label}  {self._short_reset(label, quota)}" for label, quota, _ in available)
            self._draw_centered(painter, QRectF(panel.left() + 12, divider_y + 3, panel.width() - 24, 20), reset_text, self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        self._draw_centered(painter, QRectF(panel.left() + 12, panel.bottom() - 26, panel.width() - 24, 20), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 10, QFont.Weight.DemiBold), text)

    def _paint_mini(self, painter, surface, edge, track, primary, secondary, text, muted):
        """极简圆环 B：左侧额度，右侧今日用量。"""
        panel = self._draw_panel(painter, surface, edge, 18)
        available = self._available_quotas(secondary, primary)
        ring_bounds = QRectF(panel.left() + 8, panel.center().y() - 78, 156, 156)
        rings = self._draw_rings(painter, ring_bounds, primary, secondary, track, 8)
        if len(rings) == 2:
            self._draw_centered(painter, QRectF(panel.left() + 38, panel.top() + 55, 96, 28), f"{self._quota_value(self._q5):.0f}%", self._scaled_font("Segoe UI Variable Display", 19, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(panel.left() + 38, panel.top() + 96, 96, 28), f"{self._quota_value(self._q7):.0f}%", self._scaled_font("Segoe UI Variable Display", 19, QFont.Weight.Bold), primary)
        elif available:
            label, quota, color = available[0]
            self._draw_centered(painter, QRectF(panel.left() + 28, panel.center().y() - 25, 116, 50), f"{self._quota_value(quota):.0f}%", self._scaled_font("Segoe UI Variable Display", 29, QFont.Weight.Bold), text)
            self._draw_badge(painter, QRectF(panel.left() + 43, panel.center().y() + 29, 86, 22), self._short_reset(label, quota), text, muted, edge)
        else:
            self._draw_centered(painter, ring_bounds.adjusted(26, 26, -26, -26), "暂无额度", self._scaled_font("Microsoft YaHei", 9), muted)
        divider_x = panel.left() + 171
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(divider_x, panel.top() + 24, divider_x, panel.bottom() - 24))
        self._draw_centered(painter, QRectF(divider_x + 9, panel.top() + 47, panel.right() - divider_x - 18, 25), "今日", self._scaled_font("Microsoft YaHei", 11, QFont.Weight.DemiBold), muted)
        self._draw_centered(painter, QRectF(divider_x + 7, panel.top() + 74, panel.right() - divider_x - 14, 39), self._today, self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), text)
        if len(available) == 2:
            badge_width = panel.right() - divider_x - 18
            self._draw_badge(painter, QRectF(divider_x + 9, panel.top() + 119, badge_width, 22), self._short_reset("5H", self._q5), text, muted, edge)
            self._draw_badge(painter, QRectF(divider_x + 9, panel.top() + 146, badge_width, 22), self._short_reset("7D", self._q7), text, muted, edge)

    def _paint_capsule(self, painter, surface, edge, track, primary, secondary, text, muted):
        panel = self._draw_panel(painter, surface, edge, 28)
        ring_bounds = QRectF(panel.left() + 7, panel.top() + 7, panel.height() - 14, panel.height() - 14)
        rings = self._ring_layout(ring_bounds, primary, secondary)
        _width, height = self._layout_size()
        ring_width = max(5, height * 0.048)
        for ring, quota, color, _label in rings:
            self._draw_ring(painter, ring, quota, color, track, ring_width)
        if len(rings) == 2:
            self._draw_centered(painter, QRectF(ring_bounds.left() + 16, ring_bounds.top() + 25, ring_bounds.width() - 32, 24), f"5H {self._quota_value(self._q5):.0f}%", self._scaled_font("Segoe UI Variable", 8, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(ring_bounds.left() + 16, ring_bounds.top() + 51, ring_bounds.width() - 32, 24), f"7D {self._quota_value(self._q7):.0f}%", self._scaled_font("Segoe UI Variable", 9, QFont.Weight.Bold), primary)
        else:
            active = self._q7 or self._q5
            active_value = self._quota_value(active)
            self._draw_centered(
                painter, ring_bounds.adjusted(12, 17, -12, -17),
                "--" if active_value is None else f"{active_value:.0f}%",
                self._scaled_font("Segoe UI Variable Display", 18, QFont.Weight.Bold), text,
            )

        content_left = ring_bounds.right() + 16
        content_width = panel.right() - content_left - 14
        self._draw_text(
            painter, QRectF(content_left, panel.top() + 10, content_width - 34, 29), f"今日 {self._today}",
            self._scaled_font("Microsoft YaHei", 15, QFont.Weight.Bold), text,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._draw_text(
            painter, QRectF(panel.right() - 50, panel.top() + 13, 34, 18), self._mode_label(),
            self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), primary,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        available = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        available = [item for item in available if item[1] is not None]
        row_y = panel.top() + (43 if len(available) == 2 else 57)
        row_step = 27
        for index, (label, quota, color) in enumerate(available):
            y = row_y + index * row_step
            value = self._quota_value(quota)
            self._draw_tone_badge(painter, QRectF(content_left, y, 76, 22), f"{label} {value:.0f}%", color, edge)
            self._draw_badge(painter, QRectF(content_left + 82, y, content_width - 82, 22), self._short_reset(label, quota), text, muted, edge)

    def _paint_tracks(self, painter, surface, edge, track, primary, secondary, text, muted):
        panel = self._draw_panel(painter, surface, edge, 18)
        divider_x = panel.left() + 102
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(divider_x, panel.top() + 16, divider_x, panel.bottom() - 16))
        self._draw_centered(painter, QRectF(panel.left() + 12, panel.top() + 38, 78, 24), "今日", self._scaled_font("Microsoft YaHei", 10), muted)
        self._draw_centered(painter, QRectF(panel.left() + 10, panel.top() + 66, 82, 42), self._today, self._scaled_font("Segoe UI Variable Display", 25, QFont.Weight.Bold), text)
        rows = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        rows = [item for item in rows if item[1] is not None]
        if not rows:
            self._draw_centered(painter, QRectF(divider_x + 8, 47, panel.right() - divider_x - 16, 34), "暂无可验证额度", self._scaled_font("Microsoft YaHei", 9), muted)
        else:
            content_left = divider_x + 17
            content_width = panel.right() - content_left - 16
            start_y = panel.top() + (34 if len(rows) == 2 else 68)
            step = 68
            for index, (label, quota, color) in enumerate(rows):
                y = start_y + index * step
                value = self._quota_value(quota)
                self._draw_text(painter, QRectF(content_left, y - 12, content_width, 22), f"{label}  {value:.0f}%", self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                _width, height = self._layout_size()
                self._draw_track(painter, QRectF(content_left, y + 14, content_width, 8), value, color, track, max(7, height * 0.045))
                self._draw_badge(painter, QRectF(content_left, y + 27, min(106, content_width), 22), self._short_reset(label, quota), text, muted, edge)

    def _paint_orb_a(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Information disk A: no Today text and no information outside the ring."""
        circle = self._draw_circle_panel(painter, surface, edge)
        available = self._available_quotas(secondary, primary)
        center_x = circle.center().x()
        if len(available) == 2:
            self._draw_rings(painter, circle.adjusted(22, 22, -22, -22), primary, secondary, track, 8)
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 61, 116, 17), "5H", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 78, 132, 30), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), text)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(QLineF(center_x - 38, circle.top() + 114, center_x + 38, circle.top() + 114))
            self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 120, 116, 17), "7D", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 137, 132, 30), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 68, circle.top() + 178, 136, 16), self._short_reset("7D", self._q7), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        elif available:
            label, quota, color = available[0]
            self._draw_rings(painter, circle.adjusted(24, 24, -24, -24), primary, secondary, track, 10)
            value = self._quota_value(quota)
            self._draw_centered(painter, QRectF(center_x - 54, circle.top() + 84, 108, 20), label, self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), color)
            self._draw_centered(painter, QRectF(center_x - 68, circle.top() + 105, 136, 43), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 34, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 68, circle.top() + 166, 136, 16), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        else:
            self._draw_centered(painter, circle, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)

    def _paint_halo_c(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Dual-ring gauge C: ticks and all labels stay inside a round dial."""
        circle = self._draw_circle_panel(painter, surface, edge)
        available = self._available_quotas(secondary, primary)
        center_x = circle.center().x()
        outer_ticks = circle.adjusted(13, 13, -13, -13)
        self._draw_tick_ring(painter, outer_ticks, track)
        self._draw_tick_progress(painter, outer_ticks, self._quota_value(self._q7), primary)
        rings = self._draw_rings(painter, circle.adjusted(31, 31, -31, -31), primary, secondary, track, 8)
        if len(rings) == 2:
            inner_ticks = outer_ticks.adjusted(20, 20, -20, -20)
            self._draw_tick_ring(painter, inner_ticks, track, 30, 4)
            self._draw_tick_progress(painter, inner_ticks, self._quota_value(self._q5), secondary, 30, 4)
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            self._draw_centered(painter, QRectF(center_x - 54, circle.top() + 63, 108, 16), "5H", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 79, 132, 28), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 22, QFont.Weight.Bold), text)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(QLineF(center_x - 39, circle.top() + 113, center_x + 39, circle.top() + 113))
            self._draw_centered(painter, QRectF(center_x - 54, circle.top() + 119, 108, 16), "7D", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 135, 132, 28), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 22, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 70, circle.top() + 175, 140, 16), self._short_reset("7D", self._q7), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        elif available:
            label, quota, color = available[0]
            value = self._quota_value(quota)
            self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 91, 116, 20), label, self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), color)
            self._draw_centered(painter, QRectF(center_x - 72, circle.top() + 112, 144, 43), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 34, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 70, circle.top() + 171, 140, 16), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        else:
            self._draw_centered(painter, circle, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)

    def _paint_mini_c(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Minimal ring C: sparse split values within the circle only."""
        circle = self._draw_circle_panel(painter, surface, edge)
        available = self._available_quotas(secondary, primary)
        center_x = circle.center().x()
        rings = self._draw_rings(painter, circle.adjusted(24, 24, -24, -24), primary, secondary, track, 8)
        if len(rings) == 2:
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(QLineF(center_x, circle.top() + 74, center_x, circle.top() + 143))
            self._draw_centered(painter, QRectF(center_x - 76, circle.top() + 78, 70, 18), "5H", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(center_x - 78, circle.top() + 97, 76, 30), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 22, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x + 6, circle.top() + 78, 70, 18), "7D", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(center_x + 2, circle.top() + 97, 76, 30), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 22, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 70, circle.top() + 157, 140, 16), self._short_reset("7D", self._q7), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        elif available:
            label, quota, color = available[0]
            value = self._quota_value(quota)
            self._draw_centered(painter, QRectF(center_x - 54, circle.top() + 88, 108, 20), label, self._scaled_font("Segoe UI Variable", 12, QFont.Weight.Bold), color)
            self._draw_centered(painter, QRectF(center_x - 70, circle.top() + 109, 140, 42), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 34, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 70, circle.top() + 164, 140, 16), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
        else:
            self._draw_centered(painter, circle, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)

    def _paint_capsule_b(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Status capsule B: compact meter bands, deliberately no circular gauge."""
        panel = self._draw_panel(painter, surface, edge, 28)
        divider_x = panel.left() + 76
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(divider_x, panel.top() + 18, divider_x, panel.bottom() - 18))
        self._draw_centered(painter, QRectF(panel.left() + 10, panel.top() + 43, 56, 17), "今日", self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), muted)
        self._draw_centered(painter, QRectF(panel.left() + 8, panel.top() + 61, 60, 30), self._today, self._scaled_font("Segoe UI Variable Display", 17, QFont.Weight.Bold), text)
        rows = self._available_quotas(secondary, primary)
        content_left = divider_x + 16
        reset_left = panel.right() - 48
        content_width = reset_left - content_left - 8
        start_y = panel.top() + (42 if len(rows) == 2 else 69)
        for index, (label, quota, color) in enumerate(rows):
            y = start_y + index * 42
            value = self._quota_value(quota)
            self._draw_text(painter, QRectF(content_left, y - 16, 32, 17), label, self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._draw_track(painter, QRectF(content_left + 34, y - 7, content_width - 34, 8), value, color, track, 6)
            self._draw_text(painter, QRectF(content_left + 34, y + 3, content_width - 34, 15), f"{value:.0f}%", self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._draw_centered(painter, QRectF(reset_left, y - 10, 38, 28), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 7, QFont.Weight.DemiBold), muted)
        if not rows:
            self._draw_centered(painter, QRectF(content_left, panel.top() + 59, content_width, 24), "暂无额度", self._scaled_font("Microsoft YaHei", 9), muted)

    def _paint_tracks_b(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Double-track card B: integrated header and vertically stacked tracks."""
        panel = self._draw_panel(painter, surface, edge, 18)
        self._draw_text(painter, QRectF(panel.left() + 18, panel.top() + 17, 126, 22), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 12, QFont.Weight.Bold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._draw_text(painter, QRectF(panel.right() - 70, panel.top() + 18, 52, 18), self._mode_label(), self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), muted, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(panel.left() + 18, panel.top() + 47, panel.right() - 18, panel.top() + 47))
        rows = self._available_quotas(secondary, primary)
        if not rows:
            self._draw_centered(painter, QRectF(panel.left() + 18, panel.top() + 73, panel.width() - 36, 30), "暂无可验证额度", self._scaled_font("Microsoft YaHei", 9), muted)
            return
        content_left = panel.left() + 18
        content_width = panel.width() - 36
        start_y = panel.top() + (75 if len(rows) == 2 else 103)
        for index, (label, quota, color) in enumerate(rows):
            y = start_y + index * 58
            value = self._quota_value(quota)
            self._draw_text(painter, QRectF(content_left, y - 18, 70, 18), f"{label}  {value:.0f}%", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._draw_text(painter, QRectF(content_left + 72, y - 18, content_width - 72, 18), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._draw_track(painter, QRectF(content_left, y + 7, content_width, 8), value, color, track, 7)

    def _paint_orb_a_prototype(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Prototype A: a generous information disk with a centered quota stack."""
        circle = self._draw_circle_panel(painter, surface, edge)
        center_x = circle.center().x()
        if self._q5 is not None and self._q7 is not None:
            outer = circle.adjusted(30, 30, -30, -30)
            inner = circle.adjusted(52, 52, -52, -52)
            self._draw_ring(painter, outer, self._q7, primary, track, 9)
            self._draw_ring(painter, inner, self._q5, secondary, track, 9)
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 62, 116, 17), "5H", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 78, 132, 30), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), text)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(QLineF(center_x - 38, circle.top() + 114, center_x + 38, circle.top() + 114))
            self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 120, 116, 17), "7D", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 137, 132, 30), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 23, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 67, circle.top() + 178, 134, 16), self._short_reset("7D", self._q7), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
            return
        quota = self._q7 or self._q5
        if quota is None:
            self._draw_centered(painter, circle, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)
            return
        label, color = ("7D", primary) if self._q7 is not None else ("5H", secondary)
        self._draw_ring(painter, circle.adjusted(24, 24, -24, -24), quota, color, track, 12)
        value = self._quota_value(quota)
        self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 74, 116, 22), label, self._scaled_font("Segoe UI Variable", 14, QFont.Weight.Bold), color)
        self._draw_centered(painter, QRectF(center_x - 76, circle.top() + 96, 152, 50), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 40, QFont.Weight.Bold), text)
        self._draw_centered(painter, QRectF(center_x - 72, circle.top() + 163, 144, 18), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 9, QFont.Weight.DemiBold), muted)

    def _paint_halo_c_prototype(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Prototype C: numeric outer dial and contained 5H/7D gauge hierarchy."""
        circle = self._draw_circle_panel(painter, surface, edge)
        center_x = circle.center().x()
        outer_ticks = circle.adjusted(15, 15, -15, -15)
        self._draw_tick_ring(painter, outer_ticks, track, 40, 5)
        if self._q5 is not None and self._q7 is not None:
            outer_ring = circle.adjusted(31, 31, -31, -31)
            inner_ring = circle.adjusted(53, 53, -53, -53)
            inner_ticks = circle.adjusted(34, 34, -34, -34)
            self._draw_ring(painter, outer_ring, self._q7, primary, track, 8)
            self._draw_ring(painter, inner_ring, self._q5, secondary, track, 8)
            self._draw_tick_progress(painter, outer_ticks, self._quota_value(self._q7), primary, 40, 5)
            self._draw_tick_ring(painter, inner_ticks, track, 30, 4)
            self._draw_tick_progress(painter, inner_ticks, self._quota_value(self._q5), secondary, 30, 4)
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            self._draw_centered(painter, QRectF(center_x - 54, circle.top() + 68, 108, 16), "5H", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 84, 132, 27), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 21, QFont.Weight.Bold), text)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(QLineF(center_x - 36, circle.top() + 116, center_x + 36, circle.top() + 116))
            self._draw_centered(painter, QRectF(center_x - 54, circle.top() + 121, 108, 16), "7D", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 137, 132, 27), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 21, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 175, 132, 16), self._short_reset("7D", self._q7), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
            return
        quota = self._q7 or self._q5
        if quota is None:
            self._draw_centered(painter, circle, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)
            return
        label, color = ("7D", primary) if self._q7 is not None else ("5H", secondary)
        self._draw_ring(painter, circle.adjusted(25, 25, -25, -25), quota, color, track, 10)
        self._draw_tick_progress(painter, outer_ticks, self._quota_value(quota), color, 40, 5)
        value = self._quota_value(quota)
        self._draw_centered(painter, QRectF(center_x - 58, circle.top() + 81, 116, 22), label, self._scaled_font("Segoe UI Variable", 14, QFont.Weight.Bold), color)
        self._draw_centered(painter, QRectF(center_x - 78, circle.top() + 102, 156, 50), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 40, QFont.Weight.Bold), text)
        self._draw_centered(painter, QRectF(center_x - 72, circle.top() + 166, 144, 18), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 9, QFont.Weight.DemiBold), muted)

    def _paint_mini_c_prototype(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Prototype C: a thinner concentric ring with a compact split-value core."""
        circle = self._draw_circle_panel(painter, surface, edge)
        center_x = circle.center().x()
        painter.setPen(QPen(edge, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(circle.adjusted(19, 19, -19, -19))
        if self._q5 is not None and self._q7 is not None:
            outer = circle.adjusted(31, 31, -31, -31)
            inner = circle.adjusted(51, 51, -51, -51)
            self._draw_ring(painter, outer, self._q7, primary, track, 7)
            self._draw_ring(painter, inner, self._q5, secondary, track, 7)
            q5, q7 = self._quota_value(self._q5), self._quota_value(self._q7)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(QLineF(center_x, circle.top() + 80, center_x, circle.top() + 140))
            self._draw_centered(painter, QRectF(center_x - 76, circle.top() + 81, 70, 18), "5H", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), secondary)
            self._draw_centered(painter, QRectF(center_x - 78, circle.top() + 99, 76, 28), f"{q5:.0f}%", self._scaled_font("Segoe UI Variable Display", 21, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x + 6, circle.top() + 81, 70, 18), "7D", self._scaled_font("Segoe UI Variable", 10, QFont.Weight.Bold), primary)
            self._draw_centered(painter, QRectF(center_x + 2, circle.top() + 99, 76, 28), f"{q7:.0f}%", self._scaled_font("Segoe UI Variable Display", 21, QFont.Weight.Bold), text)
            self._draw_centered(painter, QRectF(center_x - 66, circle.top() + 158, 132, 16), self._short_reset("7D", self._q7), self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
            return
        quota = self._q7 or self._q5
        if quota is None:
            self._draw_centered(painter, circle, "暂无可验证额度", self._scaled_font("Microsoft YaHei", 11), muted)
            return
        label, color = ("7D", primary) if self._q7 is not None else ("5H", secondary)
        self._draw_ring(painter, circle.adjusted(30, 30, -30, -30), quota, color, track, 9)
        value = self._quota_value(quota)
        self._draw_centered(painter, QRectF(center_x - 56, circle.top() + 81, 112, 21), label, self._scaled_font("Segoe UI Variable", 13, QFont.Weight.Bold), color)
        self._draw_centered(painter, QRectF(center_x - 74, circle.top() + 101, 148, 48), f"{value:.0f}%", self._scaled_font("Segoe UI Variable Display", 38, QFont.Weight.Bold), text)
        self._draw_centered(painter, QRectF(center_x - 72, circle.top() + 160, 144, 18), self._short_reset(label, quota), self._scaled_font("Segoe UI Variable", 9, QFont.Weight.DemiBold), muted)

    def _paint_capsule_b_prototype(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Prototype B: compact meter bands with a stable Today and Reset column."""
        panel = self._draw_panel(painter, surface, edge, 28)
        today_width = 78
        reset_width = 64
        content_left = panel.left() + today_width + 15
        content_right = panel.right() - reset_width - 10
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(panel.left() + today_width, panel.top() + 18, panel.left() + today_width, panel.bottom() - 18))
        self._draw_centered(painter, QRectF(panel.left() + 10, panel.top() + 43, today_width - 20, 16), "今日", self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), muted)
        self._draw_centered(painter, QRectF(panel.left() + 8, panel.top() + 60, today_width - 16, 30), self._today, self._scaled_font("Segoe UI Variable Display", 17, QFont.Weight.Bold), text)
        rows = self._available_quotas(secondary, primary)
        if not rows:
            self._draw_centered(painter, QRectF(content_left, panel.top() + 62, content_right - content_left, 24), "暂无额度", self._scaled_font("Microsoft YaHei", 9), muted)
            return
        start_y = panel.top() + (38 if len(rows) == 2 else 57)
        for index, (label, quota, color) in enumerate(rows):
            y = start_y + index * 43
            value = self._quota_value(quota)
            self._draw_text(painter, QRectF(content_left, y - 16, 28, 17), label, self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._draw_text(painter, QRectF(content_left + 29, y - 16, content_right - content_left - 29, 17), f"{value:.0f}%", self._scaled_font("Segoe UI Variable", 9, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._draw_track(painter, QRectF(content_left, y + 4, content_right - content_left, 8), value, color, track, 6)
            self._draw_reset_stamp(painter, QRectF(content_right + 4, y - 19, reset_width - 6, 38), label, quota, self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)

    def _paint_tracks_b_prototype(self, painter, surface, edge, track, primary, secondary, text, muted):
        """Prototype B: an integrated header and generous stacked progress tracks."""
        panel = self._draw_panel(painter, surface, edge, 18)
        self._draw_text(painter, QRectF(panel.left() + 18, panel.top() + 16, 150, 22), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 12, QFont.Weight.Bold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QLineF(panel.left() + 18, panel.top() + 47, panel.right() - 18, panel.top() + 47))
        rows = self._available_quotas(secondary, primary)
        if not rows:
            self._draw_centered(painter, QRectF(panel.left() + 18, panel.top() + 73, panel.width() - 36, 30), "暂无可验证额度", self._scaled_font("Microsoft YaHei", 9), muted)
            return
        reset_width = 58
        start_y = panel.top() + (67 if len(rows) == 2 else 78)
        row_step = 44
        for index, (label, quota, color) in enumerate(rows):
            y = start_y + index * row_step
            value = self._quota_value(quota)
            self._draw_text(painter, QRectF(panel.left() + 18, y - 18, 68, 18), f"{label}  {value:.0f}%", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            reset_rect = QRectF(panel.right() - 18 - reset_width, y - 20, reset_width, 36)
            self._draw_reset_stamp(painter, reset_rect, label, quota, self._scaled_font("Segoe UI Variable", 8, QFont.Weight.DemiBold), muted)
            self._draw_track(painter, QRectF(panel.left() + 18, y + 7, reset_rect.left() - panel.left() - 28, 8), value, color, track, 7)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pressed:
            painter.translate(self.width() / 2, self.height() / 2)
            painter.scale(.985, .985)
            painter.translate(-self.width() / 2, -self.height() / 2)
        # Every style is authored on its medium-size design canvas.  Scale the
        # complete canvas once so geometry, strokes, fonts and hit targets keep
        # the same proportions in small / medium / large presets.
        scale_x, scale_y = self._layout_scales()
        painter.scale(scale_x, scale_y)
        dark = self._theme == "dark"
        surface = QColor("#151d2b") if dark else QColor("#ffffff")
        edge = QColor("#354258") if dark else QColor("#d6e0ee")
        track = QColor("#2c3749") if dark else QColor("#e7ebf2")
        primary = QColor("#8b72ff") if dark else QColor("#705cf2")
        secondary = QColor("#44a2ff") if dark else QColor("#3188e8")
        text = QColor("#f5f7fb") if dark else QColor("#18243a")
        muted = QColor("#9cabc1") if dark else QColor("#667995")

        if self._style == "orb":
            self._paint_orb_a_prototype(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return
        if self._style == "halo":
            self._paint_halo_c_prototype(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return
        if self._style == "mini":
            self._paint_mini_c_prototype(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return
        if self._style == "capsule":
            self._paint_capsule_b_prototype(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return
        if self._style == "tracks":
            self._paint_tracks_b_prototype(painter, surface, edge, track, primary, secondary, text, muted)
            painter.end()
            return

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
        zoom_menu = menu.addMenu(f"缩放 {self._display_scale * 100:.0f}%")
        zoom_menu.addAction("缩小 5%", lambda: self.scale_change_requested.emit(round(self._display_scale - .05, 2)))
        zoom_menu.addAction("放大 5%", lambda: self.scale_change_requested.emit(round(self._display_scale + .05, 2)))
        zoom_menu.addAction("恢复 100%", lambda: self.scale_change_requested.emit(1.0))
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

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.angleDelta().y():
            delta = .05 if event.angleDelta().y() > 0 else -.05
            self.scale_change_requested.emit(round(self._display_scale + delta, 2))
            event.accept()
            return
        super().wheelEvent(event)

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
        scale_x, scale_y = self._layout_scales()
        point = QPoint(round(position.x() / scale_x), round(position.y() / scale_y))
        width, height = self._layout_size()
        if self._style == "tracks":
            zone = QRectF(16, 54, width - 32, height - 68)
            return zone.contains(point)
        if self._style == "capsule":
            zone = QRectF(92, 28, width - 150, height - 56)
            return zone.contains(point)
        center = QPoint(round(width / 2), round(height / 2))
        radius = min(width, height) * 0.38
        delta = point - center
        return delta.x() ** 2 + delta.y() ** 2 <= radius ** 2
