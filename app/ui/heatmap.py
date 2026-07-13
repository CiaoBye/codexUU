from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from app.data.models import DailyToken, format_tokens

FONT = "Microsoft YaHei"


class TokenHeatmap(QWidget):
    CELL_SIZE = 14
    CELL_GAP = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.daily_tokens = []
        self.setMinimumHeight(150)

    def set_data(self, daily_tokens):
        self.daily_tokens = daily_tokens
        self.update()

    def paintEvent(self, event):
        if not self.daily_tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        data = sorted(self.daily_tokens, key=lambda x: x.date)[-180:]
        max_val = max(d.total for d in data) if data else 1
        if max_val == 0:
            max_val = 1
        cs, cg, cols = self.CELL_SIZE, self.CELL_GAP, 7

        for i, day in enumerate(data):
            col, row = i % cols, i // cols
            x, y = col * (cs + cg) + 20, row * (cs + cg) + 20
            intensity = day.total / max_val if max_val > 0 else 0
            if day.total == 0:
                color = QColor("#1a1a2e")
            else:
                color = QColor(
                    min(255, 99 + int(156 * intensity)),
                    min(255, 102 + int(139 * (1 - intensity))),
                    241,
                )
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y, cs, cs), 3, 3)
            if day.total > 0:
                painter.setPen(QColor(255, 255, 255, 180))
                painter.setFont(QFont(FONT, 5))
                label = f"{day.total // 1000}k" if day.total >= 1000 else str(day.total)
                painter.drawText(QRectF(x, y, cs, cs), Qt.AlignmentFlag.AlignCenter, label[:3])

        self.setMinimumHeight((len(data) // cols + 1) * (cs + cg) + 40)


class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Token \u70ed\u529b\u56fe (\u8fd16\u4e2a\u6708)")
        title.setFont(QFont(FONT, 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0; padding: 8px 0;")
        layout.addWidget(title)
        self.heatmap = TokenHeatmap()
        layout.addWidget(self.heatmap)

    def set_data(self, daily_tokens):
        self.heatmap.set_data(daily_tokens)
