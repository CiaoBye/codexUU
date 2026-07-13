from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy

from app.data.models import DailyToken, format_tokens

FONT = "Microsoft YaHei"


class UsageTrendChart(QWidget):
    PADDING = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.daily_tokens = []
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, daily_tokens):
        self.daily_tokens = daily_tokens
        self.update()

    def paintEvent(self, event):
        if not self.daily_tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p = self.PADDING
        data = list(reversed(self.daily_tokens[:30]))
        max_val = max(d.total for d in data) if data else 1
        if max_val == 0:
            max_val = 1
        bar_w = max(2, (w - p * 2) / max(len(data), 1) - 2)
        chart_h = h - p * 2

        for i, day in enumerate(data):
            x = p + i * ((w - p * 2) / max(len(data), 1))
            bar_h = (day.total / max_val) * chart_h
            y = h - p - bar_h
            gradient = QLinearGradient(x, y, x, h - p)
            gradient.setColorAt(0.0, QColor("#60a5fa"))
            gradient.setColorAt(1.0, QColor("#a78bfa"))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 2, 2)

        painter.setPen(QColor("#888"))
        painter.setFont(QFont(FONT, 7))
        step = max(1, len(data) // 7)
        for i, day in enumerate(data):
            if i % step == 0:
                x = p + i * ((w - p * 2) / max(len(data), 1))
                label = day.date.strftime("%m/%d") if hasattr(day.date, "strftime") else str(day.date)[5:10]
                painter.drawText(QPointF(x, h - 5), label)

        for pct in [0, 25, 50, 75, 100]:
            y = h - p - (pct / 100) * chart_h
            val = int(max_val * pct / 100)
            painter.drawText(QPointF(2, y + 3), format_tokens(val))
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.drawLine(QPointF(p, y), QPointF(w - p, y))
            painter.setPen(QColor("#888"))


class UsageTrendWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("\u7528\u91cf\u8d8b\u52bf (\u8fd130\u5929)")
        title.setFont(QFont(FONT, 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0; padding: 8px 0;")
        layout.addWidget(title)
        self.chart = UsageTrendChart()
        layout.addWidget(self.chart)

    def set_data(self, daily_tokens):
        self.chart.set_data(daily_tokens)
