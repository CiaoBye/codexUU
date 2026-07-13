from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QWidget, QToolTip

from app.utils.statistics_timezone import get_statistics_timezone


class TokenHeatmap(QWidget):
    CELL_SIZE = 13
    CELL_GAP_X = 4
    CELL_GAP_Y = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.daily_tokens = []
        self._cells = []
        self.setMinimumHeight(160)
        self.setMinimumWidth(485)
        self.setMouseTracking(True)

    def set_data(self, daily_tokens):
        self.daily_tokens = list(daily_tokens or [])
        self.update()

    def mouseMoveEvent(self, event):
        for rect, item in self._cells:
            if rect.contains(event.position()):
                item_date = item.date.date() if hasattr(item.date, "date") else item.date
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{item_date.isoformat()}\n总量 {item.total:,}\n"
                    f"缓存 {item.cached_input:,} · 未缓存 {item.uncached_input:,} · 输出 {item.output:,}",
                    self,
                )
                return
        QToolTip.hideText()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        end = get_statistics_timezone().now_date()
        start = end - timedelta(days=179)
        start -= timedelta(days=(start.weekday() + 1) % 7)
        values = {}
        for item in self.daily_tokens:
            item_date = item.date.date() if hasattr(item.date, "date") else item.date
            values[item_date] = item
        active_values = sorted(item.total for item in self.daily_tokens if item.total > 0)

        def quantile(value: float) -> int:
            if not active_values:
                return 0
            return active_values[round((len(active_values) - 1) * value)]

        thresholds = (quantile(0.25), quantile(0.50), quantile(0.75))
        light_levels = ("#dceeff", "#b8dcff", "#78bdff", "#329fff")
        dark_levels = ("#173653", "#1d527c", "#2677ad", "#329fff")
        levels = light_levels if self._is_light() else dark_levels
        weeks = 27
        self._cells = []
        left = 32
        grid_height = 7 * self.CELL_SIZE + 6 * self.CELL_GAP_Y
        top = max(28, self.height() - 28 - grid_height)
        for column in range(weeks):
            for row in range(7):
                item_date = start + timedelta(days=column * 7 + row)
                item = values.get(item_date)
                total = item.total if item else 0
                if not item:
                    color = QColor("#f1f3f5") if self._is_light() else QColor("#202733")
                else:
                    level = sum(total > threshold for threshold in thresholds)
                    color = QColor(levels[min(3, level)])
                x = left + column * (self.CELL_SIZE + self.CELL_GAP_X)
                y = top + row * (self.CELL_SIZE + self.CELL_GAP_Y)
                rect = QRectF(x, y, self.CELL_SIZE, self.CELL_SIZE)
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, 3, 3)
                if item:
                    self._cells.append((rect, item))

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#8a94a6"))
        for row, label in enumerate(("日", "一", "二", "三", "四", "五", "六")):
            painter.drawText(QRectF(0, top + row * (self.CELL_SIZE + self.CELL_GAP_Y) - 1, 22, 16), Qt.AlignmentFlag.AlignCenter, label)
        last_month = None
        for column in range(weeks):
            month_date = start + timedelta(days=column * 7)
            if month_date.month != last_month:
                painter.drawText(
                    left + column * (self.CELL_SIZE + self.CELL_GAP_X),
                    top - 11,
                    month_date.strftime("%Y/%m"),
                )
                last_month = month_date.month

    def _is_light(self) -> bool:
        color = self.palette().window().color()
        return color.lightness() > 150
