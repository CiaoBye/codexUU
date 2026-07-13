from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QFontMetrics,
    QRadialGradient, QConicalGradient,
)
from PySide6.QtWidgets import QWidget, QSizePolicy


class ProgressRing(QWidget):
    RING_WIDTH = 12

    def __init__(
        self, parent=None,
        outer_pct: float = 0.0,
        inner_pct: float = 0.0,
        outer_color: str = "#60a5fa",
        inner_color: str = "#a78bfa",
        outer_label: str = "5h",
        inner_label: str = "7d",
        show_labels: bool = True,
        size: int = 180,
    ):
        super().__init__(parent)
        self.outer_pct = outer_pct
        self.inner_pct = inner_pct
        self.outer_color = outer_color
        self.inner_color = inner_color
        self.outer_label = outer_label
        self.inner_label = inner_label
        self.show_labels = show_labels
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_values(self, outer_pct: float, inner_pct: float):
        self.outer_pct = outer_pct
        self.inner_pct = inner_pct
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        rw = self.RING_WIDTH

        outer_r = min(w, h) / 2.0 - rw - 8
        outer_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)

        bg_pen = QPen(QColor(40, 40, 65), rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawEllipse(outer_rect)

        inner_r = outer_r - rw - 8
        inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
        painter.drawEllipse(inner_rect)

        if self.outer_pct > 0:
            span = 360.0 * self.outer_pct / 100.0
            pen = QPen(QColor(self.outer_color), rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            path = QPainterPath()
            path.arcMoveTo(outer_rect, 90)
            path.arcTo(outer_rect, 90, -span)
            painter.strokePath(path, pen)

        if self.inner_pct > 0:
            span = 360.0 * self.inner_pct / 100.0
            pen = QPen(QColor(self.inner_color), rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            path = QPainterPath()
            path.arcMoveTo(inner_rect, 90)
            path.arcTo(inner_rect, 90, -span)
            painter.strokePath(path, pen)

        if self.show_labels:
            pct_font = QFont("Microsoft YaHei", 16, QFont.Weight.Bold)
            painter.setFont(pct_font)
            painter.setPen(QColor(255, 255, 255))
            fm = QFontMetrics(pct_font)

            pct_text = f"{self.outer_pct:.0f}%"
            tw = fm.horizontalAdvance(pct_text)
            painter.drawText(QPointF(cx - tw / 2, cy - 2), pct_text)

            pct2_font = QFont("Microsoft YaHei", 12, QFont.Weight.Bold)
            painter.setFont(pct2_font)
            painter.setPen(QColor(self.inner_color))
            fm2 = QFontMetrics(pct2_font)
            pct2_text = f"{self.inner_pct:.0f}%"
            tw2 = fm2.horizontalAdvance(pct2_text)
            painter.drawText(QPointF(cx - tw2 / 2, cy + fm2.height() + 4), pct2_text)

            sub_font = QFont("Microsoft YaHei", 9)
            painter.setFont(sub_font)
            painter.setPen(QColor(140, 140, 170))
            sfm = QFontMetrics(sub_font)
            st = "剩余"
            sw = sfm.horizontalAdvance(st)
            painter.drawText(QPointF(cx - sw / 2, cy + fm2.height() + sfm.height() + 8), st)


class DualQuotaRing(QWidget):
    def __init__(self, parent=None, show_labels: bool = True):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self.ring = ProgressRing(
            self, outer_pct=0, inner_pct=0,
            outer_color="#60a5fa", inner_color="#a78bfa",
            outer_label="5h", inner_label="7d",
            show_labels=show_labels, size=180,
        )
        self.ring.move(0, 0)

    def set_quota(self, outer: float, inner: float):
        self.ring.set_values(outer, inner)

    def paintEvent(self, event):
        pass
