from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from app.data.models import format_tokens
from app.utils.statistics_timezone import get_statistics_timezone


class DesktopStatusPanel(QWidget):
    """可拖动的圆形桌面状态窗，只呈现当前 Runtime 的本机可验证状态。"""

    show_main = Signal()
    position_changed = Signal(QPoint)

    _SIZES = {"orb": 158, "halo": 174, "mini": 108}

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
        self._runtime = "Codex"
        self._today = "0"
        self._quota = None
        self._quota_label = "--"
        self._reset_label = ""
        self.set_style(self._style)

    def set_style(self, style: str):
        self._style = style if style in self._SIZES else "orb"
        size = self._SIZES[self._style]
        self.setFixedSize(size, size)
        self.update()

    def update_snapshot(self, runtime: str, snapshot):
        self._runtime = "Claude Code" if runtime == "claudeCode" else "Codex"
        self._today = format_tokens(snapshot.tokens.today.total)
        quota = snapshot.quota_7d or snapshot.quota_5h
        self._quota = quota
        self._quota_label = "7D" if snapshot.quota_7d else "5H" if snapshot.quota_5h else "--"
        self._reset_label = self._format_reset(quota)
        if quota is None:
            tip = f"{self._runtime}\n暂无可验证额度窗口\n双击打开主窗口"
        else:
            tip = (
                f"{self._runtime}\n{self._quota_label} 剩余 {quota.remaining_pct:.0f}%"
                f"\n今日 {self._today}\n{self._reset_label or '重置时间未知'}\n双击打开主窗口"
            )
        self.setToolTip(tip)
        self.update()

    @staticmethod
    def _format_reset(quota) -> str:
        if quota is None or quota.reset_time is None:
            return ""
        local_time: datetime = quota.reset_time.astimezone(get_statistics_timezone().tzinfo())
        return f"重置 {local_time.strftime('%m/%d %H:%M')}"

    def _is_dark(self) -> bool:
        return self.palette().color(self.backgroundRole()).lightness() < 128

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self._is_dark()
        surface = QColor("#182131") if dark else QColor("#f8fbff")
        edge = QColor("#3a4860") if dark else QColor("#c8d7ec")
        track = QColor("#2b3547") if dark else QColor("#e5eaf2")
        primary = QColor("#8b6df5")
        secondary = QColor("#3b9df5")
        text = QColor("#f3f6fc") if dark else QColor("#16233a")
        muted = QColor("#95a5be") if dark else QColor("#637998")

        size = min(self.width(), self.height())
        bounds = self.rect().adjusted(5, 5, -5, -5)
        if self._style == "halo":
            gradient = QRadialGradient(bounds.center(), size * 0.58)
            gradient.setColorAt(0, QColor("#514397") if dark else QColor("#e9e1ff"))
            gradient.setColorAt(0.62, surface)
            gradient.setColorAt(1, QColor(surface.red(), surface.green(), surface.blue(), 0))
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(bounds)

        painter.setBrush(surface)
        painter.setPen(QPen(edge, 1))
        painter.drawEllipse(bounds)
        ring_margin = 19 if self._style != "mini" else 13
        ring = bounds.adjusted(ring_margin, ring_margin, -ring_margin, -ring_margin)
        ring_width = 10 if self._style != "mini" else 8
        painter.setPen(QPen(track, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, 0, 360 * 16)
        if self._quota is not None:
            painter.setPen(QPen(primary, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(ring, 90 * 16, -int(360 * 16 * self._quota.remaining_pct / 100))
        if self._style == "halo" and self._quota is not None:
            outer = ring.adjusted(-12, -12, 12, 12)
            painter.setPen(QPen(QColor(secondary.red(), secondary.green(), secondary.blue(), 125), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(outer, 98 * 16, -int(300 * 16 * self._quota.remaining_pct / 100))

        if self._style != "mini":
            painter.setPen(muted)
            painter.setFont(QFont("Segoe UI Variable", 8, QFont.Weight.DemiBold))
            painter.drawText(bounds.adjusted(0, 14, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._runtime)
        value = "--" if self._quota is None else f"{self._quota.remaining_pct:.0f}%"
        painter.setPen(text)
        painter.setFont(QFont("Segoe UI Variable Display", 18 if self._style != "mini" else 15, QFont.Weight.Bold))
        value_rect = bounds.adjusted(0, -8 if self._style != "mini" else -2, 0, 10)
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, value)
        painter.setPen(muted)
        painter.setFont(QFont("Segoe UI Variable", 8, QFont.Weight.DemiBold))
        label_rect = bounds.adjusted(0, 25 if self._style != "mini" else 17, 0, 0)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._quota_label)
        if self._style != "mini":
            painter.setFont(QFont("Microsoft YaHei", 8))
            painter.drawText(bounds.adjusted(0, 0, 0, -25), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, f"今日 {self._today}")
            painter.setFont(QFont("Microsoft YaHei", 7))
            painter.drawText(bounds.adjusted(0, 0, 0, -10), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, self._reset_label)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.position_changed.emit(self.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_main.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
