from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QWidget, QToolTip

from app.utils.statistics_timezone import get_statistics_timezone


class TokenHeatmap(QWidget):
    CELL_SIZE = 15
    CELL_GAP_X = 4
    CELL_GAP_Y = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.daily_tokens = []
        self._cells = []
        # The heatmap must follow the visible card height.  A 160px minimum can
        # exceed the stacked viewport and crop the seventh row in the main app.
        self.setMinimumHeight(120)
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
        left, right = 30, 4
        available_width = max(1, self.width() - left - right)
        top, bottom = 26.0, 10.0
        available_height = max(1.0, self.height() - top - bottom)
        width_cell = (available_width - (weeks - 1) * 2.5) / weeks
        height_cell = (available_height - 6 * 2.0) / 7
        cell_size = max(8.0, min(17.0, width_cell, height_cell))
        gap_x = max(2.0, (available_width - weeks * cell_size) / (weeks - 1))
        gap_y = max(2.0, (available_height - 7 * cell_size) / 6)
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
                x = left + column * (cell_size + gap_x)
                y = top + row * (cell_size + gap_y)
                rect = QRectF(x, y, cell_size, cell_size)
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, 3, 3)
                if item:
                    self._cells.append((rect, item))
        self._layout_snapshot = {
            "cell_size": cell_size,
            "top": top,
            "grid_bottom": top + 7 * cell_size + 6 * gap_y,
            "widget_height": self.height(),
        }

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#8a94a6"))
        for row, label in enumerate(("日", "一", "二", "三", "四", "五", "六")):
            painter.drawText(QRectF(0, top + row * (cell_size + gap_y) - 1, 22, 16), Qt.AlignmentFlag.AlignCenter, label)
        last_month = None
        self._month_label_rects = []
        for column in range(weeks):
            month_date = start + timedelta(days=column * 7)
            if month_date.month != last_month:
                label_width = 54.0
                label_x = max(0.0, min(self.width() - label_width, left + column * (cell_size + gap_x) - 2))
                label_rect = QRectF(label_x, 2, label_width, 18)
                painter.drawText(
                    label_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    month_date.strftime("%Y/%m"),
                )
                self._month_label_rects.append(label_rect)
                last_month = month_date.month

    def _is_light(self) -> bool:
        color = self.palette().window().color()
        return color.lightness() > 150
