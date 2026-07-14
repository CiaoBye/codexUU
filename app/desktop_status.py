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
from PySide6.QtWidgets import QApplication, QMenu, QWidget

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
        "capsule": (270, 96),
        "tracks": (252, 132),
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
        available = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        available = [item for item in available if item[1] is not None]
        label, quota, color = available[-1] if available else ("--", None, primary)
        value = self._quota_value(quota)
        ring = QRectF(15, 14, self.height() - 28, self.height() - 28)
        ring_width = max(6, self.height() * 0.075)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(track, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, 0, 360 * 16)
        if value is not None:
            painter.setPen(QPen(color, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(ring, *self._arc(value))
        value_text = "--" if value is None else f"{value:.0f}%"
        self._draw_centered(painter, ring.adjusted(5, 8, -5, -8), value_text, self._scaled_font("Segoe UI Variable Display", 19, QFont.Weight.Bold), text)
        content_left = ring.right() + 15
        content_width = panel.right() - content_left - 16
        self._draw_text(painter, QRectF(content_left, 16, content_width, 20), self._runtime, self._scaled_font("Microsoft YaHei", 10, QFont.Weight.Bold), text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._draw_text(painter, QRectF(content_left, 16, content_width, 20), self._mode_label(), self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), color, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        summary = "  ·  ".join(f"{item_label} {self._quota_value(item_quota):.0f}%" for item_label, item_quota, _ in available) or "暂无额度"
        self._draw_text(painter, QRectF(content_left, 37, content_width, 18), summary, self._scaled_font("Segoe UI Variable", 9, QFont.Weight.DemiBold), color, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        reset = self._format_reset(quota).replace("重置 ", "") or "暂无重置时间"
        self._draw_text(painter, QRectF(content_left, 55, content_width, 17), f"{label} 重置 {reset}", self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), muted, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._draw_text(painter, QRectF(content_left, 72, content_width, 14), f"今日 {self._today}", self._scaled_font("Microsoft YaHei", 8), muted, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def _paint_tracks(self, painter, surface, edge, track, primary, secondary, text, muted):
        panel = QRectF(5, 5, self.width() - 10, self.height() - 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50 if self._theme == "dark" else 24))
        painter.drawRoundedRect(panel.translated(0, 2), 18, 18)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(surface)
        painter.drawRoundedRect(panel, 18, 18)
        painter.setPen(text)
        painter.setFont(self._scaled_font("Microsoft YaHei", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(17, 13, panel.width() - 88, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._runtime)
        self._draw_centered(painter, QRectF(panel.right() - 66, 13, 52, 22), self._mode_label(), self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), primary)
        rows = [("5H", self._q5, secondary), ("7D", self._q7, primary)]
        rows = [item for item in rows if item[1] is not None]
        if not rows:
            self._draw_centered(painter, QRectF(18, 47, panel.width() - 26, 34), "暂无可验证额度", self._scaled_font("Microsoft YaHei", 9), muted)
        else:
            start_y = 48 if len(rows) == 2 else 61
            step = 32
            for index, (label, quota, color) in enumerate(rows):
                y = start_y + index * step
                value = self._quota_value(quota)
                painter.setPen(color)
                painter.setFont(self._scaled_font("Segoe UI Variable", 9, QFont.Weight.DemiBold))
                painter.drawText(QRectF(18, y - 12, 34, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
                value_text = "--" if value is None else f"{value:.0f}%"
                painter.drawText(QRectF(panel.right() - 58, y - 12, 44, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value_text)
                self._draw_track(painter, QRectF(55, y - 2, panel.width() - 121, 8), value, color, track, max(6, self.height() * 0.05))
                if len(rows) == 1:
                    reset = self._format_reset(quota) or "重置时间未知"
                    self._draw_text(painter, QRectF(55, y + 8, panel.width() - 72, 16), reset, self._scaled_font("Microsoft YaHei", 8), muted, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.setPen(muted)
        painter.setFont(self._scaled_font("Microsoft YaHei", 8))
        painter.drawText(QRectF(18, panel.bottom() - 27, panel.width() - 32, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"今日 {self._today}")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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
            gauge = bounds.adjusted(diameter * 0.13, diameter * 0.13, -diameter * 0.13, -diameter * 0.13)
            width = diameter * 0.065
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(track, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(gauge, 0, 360 * 16)
            if active_value is not None:
                painter.setPen(QPen(active_color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawArc(gauge, *self._arc(active_value))
            self._draw_centered(painter, QRectF(diameter * 0.21, diameter * 0.27, diameter * 0.58, diameter * 0.13), f"{active_label} · {self._mode_label()}", self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), active_color)
            value_text = "--" if active_value is None else f"{active_value:.0f}%"
            self._draw_centered(painter, QRectF(diameter * 0.16, diameter * 0.40, diameter * 0.68, diameter * 0.23), value_text, self._scaled_font("Segoe UI Variable Display", 28, QFont.Weight.Bold), text)
            reset = self._format_reset(active_quota).replace("重置 ", "") or "暂无重置时间"
            self._draw_centered(painter, QRectF(diameter * 0.17, diameter * 0.65, diameter * 0.66, diameter * 0.14), reset, self._scaled_font("Microsoft YaHei", 10, QFont.Weight.DemiBold), muted)
        elif self._style == "halo":
            ring_width = diameter * 0.052
            if len(available) == 2:
                rings = (
                    (bounds.adjusted(diameter * 0.10, diameter * 0.10, -diameter * 0.10, -diameter * 0.10), available[0]),
                    (bounds.adjusted(diameter * 0.22, diameter * 0.22, -diameter * 0.22, -diameter * 0.22), available[1]),
                )
            elif available:
                rings = ((bounds.adjusted(diameter * 0.15, diameter * 0.15, -diameter * 0.15, -diameter * 0.15), available[0]),)
            else:
                rings = ()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for ring, (_, quota, color) in rings:
                painter.setPen(QPen(track, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawArc(ring, 0, 360 * 16)
                value = self._quota_value(quota)
                painter.setPen(QPen(color, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawArc(ring, *self._arc(value))
            if len(available) == 2:
                q5_value = self._quota_value(self._q5)
                q7_value = self._quota_value(self._q7)
                self._draw_centered(painter, QRectF(diameter * 0.27, diameter * 0.29, diameter * 0.46, diameter * 0.15), f"5H  {q5_value:.0f}%", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), secondary)
                self._draw_centered(painter, QRectF(diameter * 0.27, diameter * 0.44, diameter * 0.46, diameter * 0.15), f"7D  {q7_value:.0f}%", self._scaled_font("Segoe UI Variable", 11, QFont.Weight.Bold), primary)
                reset = self._format_reset(self._q7).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter * 0.25, diameter * 0.61, diameter * 0.50, diameter * 0.11), reset, self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), muted)
            else:
                value_text = "--" if active_value is None else f"{active_value:.0f}%"
                self._draw_centered(painter, QRectF(diameter * 0.22, diameter * 0.38, diameter * 0.56, diameter * 0.22), value_text, self._scaled_font("Segoe UI Variable Display", 24, QFont.Weight.Bold), text)
                self._draw_centered(painter, QRectF(diameter * 0.28, diameter * 0.28, diameter * 0.44, diameter * 0.12), f"{active_label} · {self._mode_label()}", self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), active_color)
                reset = self._format_reset(active_quota).replace("重置 ", "") or "--"
                self._draw_centered(painter, QRectF(diameter * 0.22, diameter * 0.61, diameter * 0.56, diameter * 0.13), reset, self._scaled_font("Microsoft YaHei", 9, QFont.Weight.DemiBold), muted)
            if len(available) == 2:
                self._draw_centered(painter, QRectF(diameter * 0.30, diameter * 0.72, diameter * 0.40, diameter * 0.10), self._mode_label(), self._scaled_font("Microsoft YaHei", 8), muted)
        else:
            ring = bounds.adjusted(diameter * 0.12, diameter * 0.12, -diameter * 0.12, -diameter * 0.12)
            width = diameter * 0.068
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(track, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(ring, 0, 360 * 16)
            if active_value is not None:
                painter.setPen(QPen(active_color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawArc(ring, *self._arc(active_value))
            self._draw_centered(painter, QRectF(0, diameter * 0.25, diameter, diameter * 0.18), f"{active_label} · {self._mode_label()}", self._scaled_font("Microsoft YaHei", 8, QFont.Weight.DemiBold), active_color)
            value_text = "--" if active_value is None else f"{active_value:.0f}%"
            self._draw_centered(painter, QRectF(0, diameter * 0.42, diameter, diameter * 0.25), value_text, self._scaled_font("Segoe UI Variable Display", 20, QFont.Weight.Bold), text)
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
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if self._press_position is not None and (event.position().toPoint() - self._press_position).manhattanLength() > 4:
                self._dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._suppress_release:
            self._suppress_release = False
            self._drag_start = None
            self._press_position = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            click_position = event.position().toPoint()
            should_toggle = not self._dragged and self._mode_hit_test(click_position)
            self._drag_start = None
            self._press_position = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if self._dragged:
                self.position_changed.emit(self.pos())
            else:
                self._pending_click_center = should_toggle
                self._click_timer.start(QApplication.doubleClickInterval())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self._suppress_release = True
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
