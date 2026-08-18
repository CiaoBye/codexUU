from __future__ import annotations
import math
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QFontMetrics,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

F = "Microsoft YaHei"


class ProgressRing(QWidget):
    RW = 10

    def __init__(self, parent=None, outer_pct=0.0, inner_pct=0.0,
                 outer_color="#60a5fa", inner_color="#a78bfa", size=180):
        super().__init__(parent)
        self.outer_pct = outer_pct
        self.inner_pct = inner_pct
        self.outer_color = outer_color
        self.inner_color = inner_color
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_values(self, o, i):
        self.outer_pct, self.inner_pct = o, i
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        rw = self.RW

        outer_r = min(w, h) / 2.0 - rw - 10
        outer_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)

        bg = QColor(35, 35, 60)
        p.setPen(QPen(bg, rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(outer_rect)

        inner_r = outer_r - rw - 8
        inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
        p.drawEllipse(inner_rect)

        if self.outer_pct > 0:
            span = 360.0 * self.outer_pct / 100.0
            p.setPen(QPen(QColor(self.outer_color), rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            path = QPainterPath()
            path.arcMoveTo(outer_rect, 90)
            path.arcTo(outer_rect, 90, -span)
            p.strokePath(path, p.pen())

        if self.inner_pct > 0:
            span = 360.0 * self.inner_pct / 100.0
            p.setPen(QPen(QColor(self.inner_color), rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            path = QPainterPath()
            path.arcMoveTo(inner_rect, 90)
            path.arcTo(inner_rect, 90, -span)
            p.strokePath(path, p.pen())

        f1 = QFont(F, 18, QFont.Weight.Bold)
        p.setFont(f1)
        p.setPen(QColor(255, 255, 255))
        t1 = f"{self.outer_pct:.0f}%"
        fm1 = QFontMetrics(f1)
        p.drawText(QPointF(cx - fm1.horizontalAdvance(t1) / 2, cy - 4), t1)

        f2 = QFont(F, 13, QFont.Weight.Bold)
        p.setFont(f2)
        p.setPen(QColor(self.inner_color))
        t2 = f"{self.inner_pct:.0f}%"
        fm2 = QFontMetrics(f2)
        p.drawText(QPointF(cx - fm2.horizontalAdvance(t2) / 2, cy + fm1.height() + 4), t2)

        f3 = QFont(F, 9)
        p.setFont(f3)
        p.setPen(QColor(120, 120, 160))
        t3 = "\u5269\u4f59"
        fm3 = QFontMetrics(f3)
        p.drawText(QPointF(cx - fm3.horizontalAdvance(t3) / 2, cy + fm1.height() + fm2.height() + 10), t3)


class DualQuotaRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self.ring = ProgressRing(self, size=180)
        self.ring.move(0, 0)

    def set_quota(self, o, i):
        self.ring.set_values(o, i)

    def paintEvent(self, event):
        pass
