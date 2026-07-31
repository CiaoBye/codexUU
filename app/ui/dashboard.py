from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QObject,
    QThread,
    Signal,
    Slot,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.data.codex_reader import (
    clear_cache as clear_codex_cache,
    read_codex_snapshot,
    read_daily_tokens,
    read_model_usage,
    read_projects,
    read_skill_usage,
    read_task_board,
    read_tool_usage,
)
from app.data.ccswitch_reader import (
    clear_cache as clear_ccswitch_cache,
    read_ccswitch_snapshot,
)
from app.data.models import (
    DailyToken,
    FULL_MONTHLY_VALUE,
    MultiRuntimeUsageSnapshot,
    QUOTA_STATUS_AVAILABLE,
    QUOTA_STATUS_EXHAUSTED,
    RuntimeScope,
    TokenBreakdown,
    estimate_model_api_value,
    format_tokens,
    is_gpt_model,
)
from app.ui.project_ranking import ProjectRankingWidget
from app.ui.skill_usage import SkillUsageWidget
from app.ui.task_board import TaskBoardWidget
from app.ui.usage_chart import UsageTrendWidget
from app.utils.statistics_timezone import get_statistics_timezone


ICONS_DIR = Path(__file__).resolve().parents[2] / "resources" / "icons"


def icon_path(name: str) -> str:
    return str(ICONS_DIR / name)


def icon_label(name: str, size: int = 16) -> QLabel:
    label = QLabel()
    label.setFixedSize(size, size)
    label.setPixmap(QPixmap(icon_path(name)).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
    ))
    return label


def _add_breakdown(target: TokenBreakdown, source) -> None:
    target.cached_input += int(getattr(source, "cached_input", 0) or 0)
    target.uncached_input += int(getattr(source, "uncached_input", 0) or 0)
    target.output += int(getattr(source, "output", 0) or 0)


def _model_scope_summary(models, runtime: RuntimeScope):
    """Build every visible scope number from the same fine-grained model events."""
    timezone = get_statistics_timezone()
    today = timezone.now_date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    daily_parts = defaultdict(TokenBreakdown)
    cumulative = TokenBreakdown()
    for model in models:
        _add_breakdown(cumulative, model.tokens)
        for item in model.daily_tokens:
            day = item.date.date() if hasattr(item.date, "date") else item.date
            _add_breakdown(daily_parts[day], item)

    daily = [
        DailyToken(
            date=datetime.combine(day, datetime.min.time()),
            total=parts.total,
            cached_input=parts.cached_input,
            uncached_input=parts.uncached_input,
            output=parts.output,
            runtime=runtime,
        )
        for day, parts in sorted(daily_parts.items(), reverse=True)
    ]

    def breakdown(start=None, end=today):
        result = TokenBreakdown()
        for item in daily:
            day = item.date.date()
            if day <= end and (start is None or day >= start):
                _add_breakdown(result, item)
        return result

    periods = {
        "today": breakdown(today),
        "week": breakdown(week_start),
        "month": breakdown(month_start),
        "cumulative": cumulative,
    }

    def priced_value(start=None):
        value = 0.0
        priced_tokens = 0
        total_tokens = 0
        for model in models:
            tokens = TokenBreakdown()
            if start is None:
                _add_breakdown(tokens, model.tokens)
            else:
                for item in model.daily_tokens:
                    day = item.date.date() if hasattr(item.date, "date") else item.date
                    if start <= day <= today:
                        _add_breakdown(tokens, item)
            total_tokens += tokens.total
            estimated = estimate_model_api_value(tokens, model.name)
            if estimated is not None:
                value += estimated
                priced_tokens += tokens.total
        coverage = priced_tokens / total_tokens * 100 if total_tokens else 0.0
        return round(value, 2), coverage, total_tokens - priced_tokens

    today_value, _today_coverage, _today_unpriced = priced_value(today)
    week_value, _week_coverage, _week_unpriced = priced_value(week_start)
    month_value, month_coverage, month_unpriced = priced_value(month_start)
    cumulative_value, _all_coverage, _all_unpriced = priced_value()
    return {
        "daily": daily,
        "periods": periods,
        "values": {
            "today": today_value,
            "week": week_value,
            "month": month_value,
            "cumulative": cumulative_value,
        },
        "month_coverage": month_coverage,
        "month_unpriced": month_unpriced,
    }


class RefreshWorker(QObject):
    loaded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    @Slot()
    def run(self):
        try:
            clear_codex_cache()
            clear_ccswitch_cache()
            self.loaded.emit((
                read_codex_snapshot(), read_task_board(), read_daily_tokens(), read_projects(),
                read_tool_usage(), read_skill_usage(), read_model_usage(), read_ccswitch_snapshot(),
            ))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class Surface(QFrame):
    def __init__(self, object_name: str = "surfaceCard", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


class TokenCompositionBar(QWidget):
    COLORS = (QColor("#3f95ff"), QColor("#8d74ff"), QColor("#e99a25"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = (0, 0, 0)
        self.setFixedHeight(12)

    def set_tokens(self, tokens):
        self.values = (
            int(tokens.uncached_input if tokens else 0),
            int(tokens.cached_input if tokens else 0),
            int(tokens.output if tokens else 0),
        )
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0, 2, self.width(), 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(127, 145, 172, 36))
        painter.drawRoundedRect(track, 4, 4)
        total = sum(self.values)
        if total <= 0:
            return
        clip_path = QPainterPath()
        clip_path.addRoundedRect(track, 4, 4)
        painter.save()
        painter.setClipPath(clip_path)
        widths = [self.width() * value / total if value > 0 else 0.0 for value in self.values]
        minimum = min(5.0, self.width() / max(1, sum(value > 0 for value in self.values)))
        deficit = 0.0
        for index, width in enumerate(widths):
            if 0 < width < minimum:
                deficit += minimum - width
                widths[index] = minimum
        for index in sorted(range(len(widths)), key=widths.__getitem__, reverse=True):
            removable = max(0.0, widths[index] - minimum)
            take = min(removable, deficit)
            widths[index] -= take
            deficit -= take
            if deficit <= 0:
                break
        x = 0.0
        for index, value in enumerate(self.values):
            if value <= 0:
                continue
            width = widths[index]
            segment = QRectF(x, 2, width, 8)
            painter.setBrush(self.COLORS[index])
            painter.drawRect(segment)
            x += width
        painter.restore()


class MetricCard(Surface):
    activated = Signal()

    def __init__(self, label: str, icon: str, parent=None):
        super().__init__(parent=parent)
        self.setMinimumHeight(136)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(13, 24, 45, 34))
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(4)

        header = QHBoxLayout()
        symbol = QLabel()
        symbol.setFixedSize(16, 16)
        symbol.setPixmap(QPixmap(icon_path(icon)).scaled(
            15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        header.addWidget(symbol)
        self.title = QLabel(label)
        self.title.setObjectName("metricLabel")
        header.addWidget(self.title)
        header.addStretch()
        self.value_hint = QLabel("$0")
        self.value_hint.setObjectName("caption")
        header.addWidget(self.value_hint)
        layout.addLayout(header)

        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        self.value = QLabel("0")
        self.value.setObjectName("metricValue")
        value_row.addWidget(self.value)
        value_row.addStretch()
        layout.addLayout(value_row)
        self.composition = TokenCompositionBar()
        layout.addWidget(self.composition)
        self.breakdown_rows = {}
        breakdown = QVBoxLayout()
        breakdown.setSpacing(1)
        for key, color, label in (
            ("uncached", "#3f95ff", "未缓存"),
            ("cached", "#8d74ff", "缓存"),
            ("output", "#e99a25", "输出"),
        ):
            row = QHBoxLayout()
            row.setSpacing(5)
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background:{color}; border-radius:3px;")
            row.addWidget(dot)
            name = QLabel(label)
            name.setObjectName("metricBreakdown")
            row.addWidget(name)
            row.addStretch()
            amount = QLabel("0")
            amount.setObjectName("metricBreakdown")
            amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(amount)
            breakdown.addLayout(row)
            self.breakdown_rows[key] = (name, amount)
        layout.addLayout(breakdown)
        self.language = "zh"
        self._tokens = None
        self._total_override = None
        self._display_total = 0
        self._value_animation = None
        self.reduce_motion = False

    def update_value(self, tokens, estimated_value: float, total_override: int | None = None):
        self._tokens = tokens
        self._total_override = total_override
        detail_total = tokens.total if tokens else 0
        display_total = total_override if total_override is not None else detail_total
        self._animate_total(display_total)
        self.value_hint.setText(f"${estimated_value:,.2f}" if estimated_value else "$0")
        self.composition.set_tokens(tokens)
        self._update_detail()
        if total_override is not None:
            self.value.setToolTip(
                f"All-time total {display_total:,} · classified {detail_total:,}"
                if self.language == "en"
                else f"累计总量 {display_total:,} · 分类明细 {detail_total:,}"
            )
        else:
            self.value.setToolTip("")

    def set_language(self, language):
        self.language = language
        self._update_detail()

    def set_reduce_motion(self, enabled):
        self.reduce_motion = bool(enabled)

    def _animate_total(self, target):
        target = int(target or 0)
        if self.reduce_motion or self._display_total == 0:
            self._display_total = target
            self.value.setText(format_tokens(target))
            return
        animation = QVariantAnimation(self)
        animation.setDuration(320)
        animation.setStartValue(self._display_total)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(lambda value: self.value.setText(format_tokens(int(value))))
        animation.finished.connect(lambda: setattr(self, "_display_total", target))
        self._value_animation = animation
        animation.start()

    def _update_detail(self):
        tokens = self._tokens
        values = (
            format_tokens(tokens.uncached_input) if tokens else "0",
            format_tokens(tokens.cached_input) if tokens else "0",
            format_tokens(tokens.output) if tokens else "0",
        )
        labels = ("Uncached", "Cached", "Output") if self.language == "en" else ("未缓存", "缓存", "输出")
        for key, label, value in zip(("uncached", "cached", "output"), labels, values):
            name, amount = self.breakdown_rows[key]
            name.setText(label)
            amount.setText(value)
            name.setToolTip(f"{label} {value}")
            amount.setToolTip(f"{label} {value}")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)


class QuotaDial(QWidget):
    center_activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.q5 = None
        self.q7 = None
        self.month = None
        self.quota_status = "unavailable"
        self.language = "zh"
        self.display_mode = "remaining"
        self.provider_mode = False
        self.provider_name = ""
        self.provider_balance = None
        self.provider_status = "unavailable"
        self.provider_status_detail = ""
        self.single_ring_rect = QRectF()
        # The summary card has a fixed vertical budget.  Keep the dial flexible
        # so Qt never satisfies its minimum height by painting underneath the
        # reset strip.
        self.setMinimumSize(190, 138)

    def set_quota(self, q5, q7, status=None, month=None):
        self.q5, self.q7 = q5, q7
        self.month = month
        self.provider_mode = False
        self.provider_name = ""
        self.provider_balance = None
        self.provider_status = "unavailable"
        self.provider_status_detail = ""
        self.quota_status = status or (QUOTA_STATUS_AVAILABLE if q5 is not None or q7 is not None or month is not None else "unavailable")
        self.update()

    def set_provider(self, snapshot):
        self.q5 = self.q7 = self.month = None
        self.provider_mode = True
        self.provider_name = str(getattr(snapshot, "provider_name", "") or "")
        self.provider_balance = getattr(snapshot, "balance", None)
        self.provider_status = str(getattr(snapshot, "status", "unavailable") or "unavailable")
        self.provider_status_detail = str(getattr(snapshot, "status_detail", "") or "")
        self.update()

    def set_language(self, language):
        self.language = language
        self.update()

    def set_display_mode(self, mode):
        self.display_mode = mode if mode in ("remaining", "used") else "remaining"
        self.update()

    def _paint_provider(self, painter):
        text_color = QColor("#172033") if self.palette().window().color().lightness() > 128 else QColor("#f8fafc")
        center = QPointF(self.width() / 2, self.height() / 2)
        balance = self.provider_balance
        if balance is None or balance.remaining is None:
            painter.setPen(QColor("#d96b3b") if self.provider_status == "degraded" else text_color)
            painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.DemiBold))
            label = "Balance unavailable" if self.language == "en" else "\u4e2d\u8f6c\u4f59\u989d\u4e0d\u53ef\u9a8c\u8bc1"
            painter.drawText(QRectF(center.x() - 92, center.y() - 18, 184, 26), Qt.AlignmentFlag.AlignCenter, label)
            painter.setPen(text_color)
            painter.setFont(QFont("Microsoft YaHei", 8))
            detail = self.provider_status_detail or ("Waiting for provider data" if self.language == "en" else "\u7b49\u5f85\u4e2d\u8f6c\u6570\u636e")
            painter.drawText(QRectF(center.x() - 102, center.y() + 12, 204, 24), Qt.AlignmentFlag.AlignCenter, detail)
            return

        side = max(80.0, min(self.width(), self.height()) - 12.0)
        bounds = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        total = getattr(balance, "total", None)
        remaining = max(0.0, float(balance.remaining))
        if total is not None and float(total) > 0:
            ratio = max(0.0, min(1.0, remaining / float(total)))
            rect = bounds.adjusted(9, 9, -9, -9)
            color = QColor("#35a58a")
            painter.setPen(QPen(QColor(53, 165, 138, 42), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 0, 360 * 16)
            painter.setPen(QPen(color, 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 270 * 16, int(360 * 16 * ratio))

        painter.setPen(QColor("#35a58a"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.DemiBold))
        caption = "Provider balance" if self.language == "en" else "\u4e2d\u8f6c\u4f59\u989d"
        painter.drawText(QRectF(center.x() - 96, center.y() - 32, 192, 20), Qt.AlignmentFlag.AlignCenter, caption)
        painter.setPen(text_color)
        amount = f"{remaining:,.2f} {getattr(balance, 'unit', None) or 'USD'}"
        painter.setFont(QFont("Segoe UI Variable Display", 23 if len(amount) < 13 else 19, QFont.Weight.Bold))
        painter.drawText(QRectF(center.x() - 108, center.y() - 5, 216, 34), Qt.AlignmentFlag.AlignCenter, amount)
        painter.setPen(QColor("#748197"))
        painter.setFont(QFont("Microsoft YaHei", 8))
        plan = getattr(balance, "plan_name", "") or self.provider_name or ("CC Switch" if self.language == "en" else "CC Switch")
        painter.drawText(QRectF(center.x() - 100, center.y() + 32, 200, 18), Qt.AlignmentFlag.AlignCenter, plan)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.provider_mode:
            self._paint_provider(painter)
            return
        available = [
            item for item in (
                ("7d", self.q7, QColor("#8d74ff")),
                ("5h", self.q5, QColor("#3992ff")),
            ) if item[1] is not None
        ]
        if not available and self.month is not None:
            available = [("month", self.month, QColor("#35a58a"))]
        single = len(available) == 1
        side = min(self.width(), self.height()) - (4 if single else 12)
        bounds = QRectF((self.width() - side) / 2, 2 if single else 3, side, side)
        self.single_ring_rect = QRectF()
        for index, (label, quota, color) in enumerate(available):
            inset = index * 20 if len(available) > 1 else 8
            rect = bounds.adjusted(inset, inset, -inset, -inset)
            width = 15 if len(available) == 1 else 11
            track_color = QColor(color)
            track_color.setAlpha(48 if len(available) == 1 else 38)
            painter.setPen(QPen(track_color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 0, 360 * 16)
            value = quota.used_pct if self.display_mode == "used" else quota.remaining_pct
            value = max(0.0, min(100.0, value))
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            direction = -1 if self.display_mode == "used" else 1
            span = direction * int(360 * 16 * value / 100)
            painter.drawArc(rect, 270 * 16, span)
            if len(available) == 1:
                self.single_ring_rect = QRectF(rect)
                if value <= 0:
                    painter.drawEllipse(QRectF(rect.center().x() - width / 2, rect.bottom() - width / 2, width, width))

        text_color = QColor("#172033") if self.palette().window().color().lightness() > 128 else QColor("#f8fafc")
        painter.setPen(text_color)
        center = bounds.center()
        if not available:
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Medium))
            exhausted = self.quota_status == QUOTA_STATUS_EXHAUSTED
            painter.setPen(QColor("#d96b3b") if exhausted else text_color)
            painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.DemiBold))
            text = "Quota exhausted" if exhausted and self.language == "en" else (
                "额度已用尽" if exhausted else ("Unavailable" if self.language == "en" else "暂不可验证")
            )
            painter.drawText(QRectF(center.x() - 82, center.y() - 18, 164, 26), Qt.AlignmentFlag.AlignCenter, text)
            painter.setPen(text_color)
            painter.setFont(QFont("Microsoft YaHei", 8))
            detail = "Waiting for reset" if exhausted and self.language == "en" else (
                "等待后端重置" if exhausted else ("No verifiable window" if self.language == "en" else "后端未返回窗口")
            )
            painter.drawText(QRectF(center.x() - 82, center.y() + 10, 164, 18), Qt.AlignmentFlag.AlignCenter, detail)
            return
        if len(available) == 1:
            label, quota, color = available[0]
            value = quota.used_pct if self.display_mode == "used" else quota.remaining_pct
            caption = f"{label.upper()} {'Usage' if self.language == 'en' else '使用率'}"
            painter.setPen(color)
            painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(center.x() - 96, center.y() - 34, 192, 22),
                Qt.AlignmentFlag.AlignCenter,
                caption,
            )
            painter.setPen(text_color)
            painter.setFont(QFont("Segoe UI Variable Display", 34, QFont.Weight.Bold))
            painter.drawText(
                QRectF(center.x() - 104, center.y() - 5, 208, 44),
                Qt.AlignmentFlag.AlignCenter,
                f"{value:.0f}%",
            )
            return

        # Scheme C: the inner 5H and outer 7D values are intentionally stacked,
        # not compressed into a single line.  This mirrors the selected prototype.
        entries = (("5H", self.q5, QColor("#3992ff"), -47), ("7D", self.q7, QColor("#8d74ff"), 13))
        for label, quota, color, offset in entries:
            if quota is None:
                continue
            value = quota.used_pct if self.display_mode == "used" else quota.remaining_pct
            caption = f"{label} {'Usage' if self.language == 'en' else '使用率'}"
            painter.setPen(color)
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(center.x() - 72, center.y() + offset, 144, 17),
                Qt.AlignmentFlag.AlignCenter,
                caption,
            )
            painter.setPen(text_color)
            painter.setFont(QFont("Segoe UI Variable Display", 20, QFont.Weight.Bold))
            painter.drawText(
                QRectF(center.x() - 78, center.y() + offset + 15, 156, 28),
                Qt.AlignmentFlag.AlignCenter,
                f"{value:.0f}%",
            )
        painter.setPen(QPen(QColor(149, 166, 193, 100), 1))
        painter.drawLine(QPointF(center.x() - 55, center.y() + 3), QPointF(center.x() + 55, center.y() + 3))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.provider_mode:
            available_count = int(self.q5 is not None) + int(self.q7 is not None) + int(self.month is not None)
            single = available_count == 1
            side = min(self.width(), self.height()) - (4 if single else 12)
            center = QPointF(self.width() / 2, (2 if single else 3) + side / 2)
            delta = event.position() - center
            if delta.x() ** 2 + delta.y() ** 2 <= (side * (.42 if single else .36)) ** 2:
                self.center_activated.emit()
                event.accept()
                return
        super().mouseReleaseEvent(event)


class QuotaResetStrip(QFrame):
    """Prototype C's dedicated reset area; adapts from two sections to one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("quotaResetStrip")
        self.setFixedHeight(52)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(6)
        self.five_section, self.five_label, self.five_time = self._section("metric-today.svg", "#3992ff")
        self.seven_section, self.seven_label, self.seven_time = self._section("metric-week.svg", "#8d74ff")
        self.month_section, self.month_label, self.month_time = self._section("metric-month.svg", "#35a58a")
        self.divider = QFrame()
        self.divider.setObjectName("quotaResetDivider")
        self.divider.setFrameShape(QFrame.Shape.VLine)
        self.month_divider = QFrame()
        self.month_divider.setObjectName("quotaResetDivider")
        self.month_divider.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(self.five_section, 1)
        layout.addWidget(self.divider)
        layout.addWidget(self.seven_section, 1)
        layout.addWidget(self.month_divider)
        layout.addWidget(self.month_section, 1)

    @staticmethod
    def _section(icon_name, color):
        section = QWidget()
        layout = QHBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch()
        icon = icon_label(icon_name, 24)
        layout.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        label = QLabel()
        label.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: 700;")
        text.addWidget(label)
        time = QLabel("--")
        time.setObjectName("quotaResetTime")
        text.addWidget(time)
        layout.addLayout(text)
        layout.addStretch()
        return section, label, time

    @staticmethod
    def _time_text(prefix, quota):
        if quota is None or quota.reset_time is None:
            return "--", ""
        local_time = quota.reset_time.astimezone(get_statistics_timezone().tzinfo())
        details = [local_time.strftime("%Y-%m-%d %H:%M:%S %Z")]
        for reset_time in quota.reset_times[1:]:
            details.append(reset_time.astimezone(get_statistics_timezone().tzinfo()).strftime("%Y-%m-%d %H:%M:%S %Z"))
        if quota.reset_count is not None and quota.reset_count > 0:
            details.insert(0, f"Available reset credits: {quota.reset_count}")
        return (
            local_time.strftime("%H:%M") if prefix == "5H" else local_time.strftime("%m/%d %H:%M"),
            "\n".join(details),
        )

    def update_values(self, q5, q7, month=None, english=False):
        self.five_section.setVisible(q5 is not None)
        self.divider.setVisible(q5 is not None and (q7 is not None or month is not None))
        self.seven_section.setVisible(q7 is not None)
        self.month_divider.setVisible(q7 is not None and month is not None)
        self.month_section.setVisible(month is not None)
        for prefix, quota, label, time, section in (
            ("5H", q5, self.five_label, self.five_time, self.five_section),
            ("7D", q7, self.seven_label, self.seven_time, self.seven_section),
            ("MONTH", month, self.month_label, self.month_time, self.month_section),
        ):
            if quota is None:
                continue
            label.setText(f"{prefix} reset time" if english else f"{prefix} 重置时间")
            value, tooltip = self._time_text(prefix, quota)
            time.setText(value)
            section.setToolTip(tooltip)


class QuotaPanel(Surface):
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(icon_label("quota.svg", 16))
        self.title = QLabel("额度使用情况")
        self.title.setObjectName("sectionTitle")
        header.addWidget(self.title)
        header.addStretch()
        layout.addLayout(header)
        self.dial = QuotaDial()
        self.dial.center_activated.connect(self._toggle_center_mode)
        layout.addWidget(self.dial, 1)
        self.reset_strip = QuotaResetStrip()
        layout.addWidget(self.reset_strip)
        self.language = "zh"
        self.q5 = None
        self.q7 = None
        self.month = None
        self.quota_status = "unavailable"
        self.display_mode = "remaining"
        self.provider_mode = False
        self.provider_snapshot = None

    def _select_mode(self, mode):
        self.set_display_mode(mode)
        self.mode_changed.emit(mode)

    def _toggle_center_mode(self):
        self._select_mode("used" if self.display_mode == "remaining" else "remaining")

    def set_display_mode(self, mode):
        self.display_mode = mode if mode in ("remaining", "used") else "remaining"
        self.dial.set_display_mode(self.display_mode)

    def update_quota(self, q5, q7, status=None, month=None):
        self.provider_mode = False
        self.provider_snapshot = None
        self.q5, self.q7 = q5, q7
        self.month = month
        self.quota_status = status or (QUOTA_STATUS_AVAILABLE if q5 is not None or q7 is not None or month is not None else "unavailable")
        self.dial.set_quota(q5, q7, self.quota_status, month)
        self.reset_strip.setVisible(True)
        english = self.language == "en"
        self.reset_strip.update_values(q5, q7, month, english)

    def update_provider(self, snapshot):
        self.provider_mode = True
        self.provider_snapshot = snapshot
        self.dial.set_provider(snapshot)
        self.reset_strip.setVisible(False)
        self._update_title()

    def _update_title(self):
        self.title.setText(
            "Provider balance" if self.provider_mode and self.language == "en" else
            "\u4e2d\u8f6c\u4f59\u989d" if self.provider_mode else
            "Quota usage" if self.language == "en" else "\u989d\u5ea6\u4f7f\u7528\u60c5\u51b5"
        )

    def set_language(self, language):
        self.language = language
        self.dial.set_language(language)
        self.set_display_mode(self.display_mode)
        if self.provider_mode:
            self._update_title()
            self.dial.set_provider(self.provider_snapshot)
        else:
            self._update_title()
            self.update_quota(self.q5, self.q7, self.quota_status, self.month)


class MilestoneProgress(QWidget):
    MILESTONES = (("Plus", 20.0), ("Pro 100", 100.0), ("Pro 200", 200.0))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.reduce_motion = False
        self._animation = None
        self.setMinimumHeight(34)

    @staticmethod
    def position(value: float) -> float:
        if value <= 20:
            return value / 20 * 0.20
        if value <= 100:
            return 0.20 + (value - 20) / 80 * 0.18
        if value <= 200:
            return 0.38 + (value - 100) / 100 * 0.15
        denominator = max(1.0, math.log10(FULL_MONTHLY_VALUE / 200))
        return min(1.0, 0.53 + math.log10(max(1, value / 200)) / denominator * 0.47)

    def set_value(self, value: float):
        target = max(0.0, value)
        if self.reduce_motion or self.value == 0:
            self.value = target
            self.update()
            return
        animation = QVariantAnimation(self)
        animation.setDuration(420)
        animation.setStartValue(self.value)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(self._set_animated_value)
        self._animation = animation
        animation.start()

    def _set_animated_value(self, value):
        self.value = float(value)
        self.update()

    def set_reduce_motion(self, enabled):
        self.reduce_motion = bool(enabled)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, y = 6, 6, 8
        width = max(1, self.width() - left - right)
        painter.setPen(QPen(QColor(127, 145, 172, 42), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(left, y, left + width, y)
        progress_x = left + width * self.position(self.value)
        milestone_colors = {
            "Plus": QColor("#2596f3"),
            "Pro 100": QColor("#8267e8"),
            "Pro 200": QColor("#b25bd6"),
        }
        previous_x = left
        previous_color = milestone_colors["Plus"]
        for label, amount in self.MILESTONES:
            segment_end = min(progress_x, left + width * self.position(amount))
            if segment_end > previous_x:
                painter.setPen(QPen(previous_color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(int(previous_x), y, int(segment_end), y)
            previous_x = left + width * self.position(amount)
            previous_color = milestone_colors[label]
            if progress_x <= previous_x:
                break
        if progress_x > previous_x:
            painter.setPen(QPen(previous_color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(int(previous_x), y, int(progress_x), y)
        painter.setFont(QFont("Microsoft YaHei", 8))
        for label, amount in self.MILESTONES:
            x = left + width * self.position(amount)
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(milestone_colors[label], 2))
            painter.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
            painter.setPen(milestone_colors[label])
            painter.drawText(QRectF(x - 34, 17, 68, 15), Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QColor("#748197"))
        painter.drawText(QRectF(self.width() - 72, 17, 68, 15), Qt.AlignmentFlag.AlignRight, "$46.5K")


class ValueCard(Surface):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setMinimumHeight(88)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 11, 15, 11)
        layout.setSpacing(7)
        header = QHBoxLayout()
        header.addWidget(icon_label("value.svg", 16))
        self.title = QLabel("羊毛进度")
        self.title.setObjectName("sectionTitle")
        header.addWidget(self.title)
        header.addStretch()
        self.value = QLabel("$0 / $46.5K")
        self.value.setStyleSheet("font-size: 20px; font-weight: 700;")
        header.addWidget(self.value)
        layout.addLayout(header)
        self.bar = MilestoneProgress()
        layout.addWidget(self.bar)
        self.hint = QLabel("按官方模型价格估算")
        self.hint.setObjectName("caption")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.hint)
        self.language = "zh"
        self.coverage = 100.0
        self.unpriced_tokens = 0
        self.provider_mode = False
        self.provider_snapshot = None

    def update_value(self, value: float, coverage: float = 100.0, unpriced_tokens: int = 0):
        self.provider_mode = False
        self.provider_snapshot = None
        self.coverage = coverage
        self.unpriced_tokens = unpriced_tokens
        self.bar.setVisible(True)
        self.value.setText(f"${value:,.2f} / $46.5K")
        self.bar.set_value(value)
        self._update_title()
        self._update_hint()

    def update_provider(self, snapshot):
        self.provider_mode = True
        self.provider_snapshot = snapshot
        self.bar.setVisible(False)
        self.value.setText(f"${snapshot.current_month_cost_usd:,.2f}")
        self.value.setToolTip(
            f"{snapshot.data_source}\n"
            f"{snapshot.request_count} requests\n"
            f"{snapshot.success_count} succeeded / {snapshot.failure_count} failed"
        )
        self._update_title()
        self._update_hint()

    def _update_title(self):
        self.title.setText(
            "Relay cost" if self.provider_mode and self.language == "en" else
            "\u4e2d\u8f6c\u6210\u672c" if self.provider_mode else
            "Value progress" if self.language == "en" else "\u7f8a\u6bdb\u8fdb\u5ea6"
        )

    def set_language(self, language):
        self.language = language
        self._update_title()
        self._update_hint()

    def set_reduce_motion(self, enabled):
        self.bar.set_reduce_motion(enabled)

    def _update_hint(self):
        if self.provider_mode:
            snapshot = self.provider_snapshot
            if snapshot is None:
                return
            self.hint.setText(
                f"{snapshot.request_count} requests · {snapshot.success_count} succeeded"
                if self.language == "en" else
                f"{snapshot.request_count} \u8bf7\u6c42 · \u6210\u529f {snapshot.success_count} \u6b21"
            )
        elif self.unpriced_tokens:
            self.hint.setText(
                f"Official price coverage {self.coverage:.0f}% · other models unpriced"
                if self.language == "en"
                else f"官方价格计价覆盖 {self.coverage:.0f}% · 其余模型未计价"
            )
        else:
            self.hint.setText("Estimated with official model prices" if self.language == "en" else "按官方模型价格估算")


class ProviderUsageLabel(QLabel):
    """Show the active CC Switch provider without mixing it into official quota."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("providerUsageBadge")
        self.setMinimumWidth(180)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.snapshot = None
        self.language = "zh"

    def set_language(self, language):
        self.language = language
        self._render()

    def set_snapshot(self, snapshot):
        self.snapshot = snapshot
        self._render()

    def _render(self):
        snapshot = self.snapshot
        english = self.language == "en"
        if snapshot is None or not snapshot.provider_name:
            self.setText("CCS: unavailable" if english else "CCS \u4e2d\u8f6c\uff1a\u672a\u68c0\u6d4b\u5230")
            self.setToolTip("")
            return
        balance = snapshot.balance
        if balance is not None and balance.remaining is not None:
            value = f"{balance.remaining:,.2f} {balance.unit or 'USD'}"
            text = f"CCS \u00b7 {snapshot.provider_name} \u00b7 {value}"
        elif snapshot.request_count:
            text = f"CCS \u00b7 {snapshot.provider_name} \u00b7 " + (
                "usage tracked" if english else "\u7528\u91cf\u5df2\u7edf\u8ba1"
            )
        else:
            text = f"CCS \u00b7 {snapshot.provider_name} \u00b7 " + (
                "quota unavailable" if english else "\u989d\u5ea6\u4e0d\u53ef\u9a8c\u8bc1"
            )
        self.setText(text)
        balance_text = (
            f"{balance.remaining:,.2f} {balance.unit or 'USD'}"
            if balance is not None and balance.remaining is not None
            else ("unavailable" if english else "\u4e0d\u53ef\u9a8c\u8bc1")
        )
        if english:
            lines = [
                f"Provider: {snapshot.provider_name}",
                f"Plan: {snapshot.plan_name or '--'}",
                f"Remaining: {balance_text}",
                f"Today tokens: {format_tokens(snapshot.tokens.today.total)}",
                f"Requests: {snapshot.request_count} ({snapshot.success_count} succeeded, {snapshot.failure_count} failed)",
                f"CCS cost: ${snapshot.current_month_cost_usd:,.4f} this month",
                f"Source: {snapshot.data_source}",
            ]
        else:
            lines = [
                f"\u4f9b\u5e94\u5546\uff1a{snapshot.provider_name}",
                f"\u5957\u9910\uff1a{snapshot.plan_name or '--'}",
                f"\u5269\u4f59\uff1a{balance_text}",
                f"\u4eca\u65e5 Token\uff1a{format_tokens(snapshot.tokens.today.total)}",
                f"\u8bf7\u6c42\uff1a{snapshot.request_count}\uff08\u6210\u529f {snapshot.success_count}\uff0c\u5931\u8d25 {snapshot.failure_count}\uff09",
                f"\u672c\u6708 CCS \u6210\u672c\uff1a${snapshot.current_month_cost_usd:,.4f}",
                f"\u6765\u6e90\uff1a{snapshot.data_source}",
            ]
        if snapshot.status_detail:
            lines.append(("Status: " if english else "\u72b6\u6001\uff1a") + snapshot.status_detail)
        self.setToolTip("\n".join(lines))


def _provider_scope_tooltip(snapshot, english: bool) -> str:
    if snapshot is None or not snapshot.provider_name:
        return "No CC Switch provider was detected" if english else "\u672a\u68c0\u6d4b\u5230 CC Switch \u4e2d\u8f6c\u7ad9"
    balance = snapshot.balance
    balance_text = (
        f"{balance.remaining:,.2f} {balance.unit or 'USD'}"
        if balance is not None and balance.remaining is not None
        else ("unavailable" if english else "\u4e0d\u53ef\u9a8c\u8bc1")
    )
    if english:
        lines = [
            f"Provider: {snapshot.provider_name}",
            f"Balance: {balance_text}",
            f"Today tokens: {format_tokens(snapshot.tokens.today.total)}",
            f"Requests: {snapshot.request_count} ({snapshot.success_count} succeeded, {snapshot.failure_count} failed)",
            f"CCS cost this month: ${snapshot.current_month_cost_usd:,.4f}",
            f"Source: {snapshot.data_source}",
            "Click to view this provider's Token data",
        ]
    else:
        lines = [
            f"\u4e2d\u8f6c\u7ad9\uff1a{snapshot.provider_name}",
            f"\u4f59\u989d\uff1a{balance_text}",
            f"\u4eca\u65e5 Token\uff1a{format_tokens(snapshot.tokens.today.total)}",
            f"\u8bf7\u6c42\uff1a{snapshot.request_count}\uff08\u6210\u529f {snapshot.success_count}\uff0c\u5931\u8d25 {snapshot.failure_count}\uff09",
            f"\u672c\u6708 CCS \u6210\u672c\uff1a${snapshot.current_month_cost_usd:,.4f}",
            f"\u6765\u6e90\uff1a{snapshot.data_source}",
            "\u70b9\u51fb\u67e5\u770b\u8be5\u4e2d\u8f6c\u7ad9 Token \u6570\u636e",
        ]
    if snapshot.status_detail:
        lines.append(("Status: " if english else "\u72b6\u6001\uff1a") + snapshot.status_detail)
    return "\n".join(lines)


class ProviderScopeButton(QPushButton):
    """A compact provider scope selector whose label comes from CCS metadata."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.language = "zh"
        self.setObjectName("topToggleButton")
        self.setCheckable(True)
        self.setMinimumWidth(58)
        self.setMaximumWidth(132)
        self.setFixedHeight(28)
        self.set_snapshot(None)

    def set_language(self, language):
        self.language = language
        self._render()

    def set_snapshot(self, snapshot):
        self.snapshot = snapshot
        self._render()

    def _render(self):
        snapshot = self.snapshot
        english = self.language == "en"
        name = str(getattr(snapshot, "provider_name", "") or "").strip()
        self.setText(name or ("Relay" if english else "\u4e2d\u8f6c"))
        self.setEnabled(bool(name))
        self.setToolTip(_provider_scope_tooltip(snapshot, english))


class AnimatedStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._animation = None
        self.reduce_motion = False

    def set_reduce_motion(self, enabled):
        self.reduce_motion = bool(enabled)

    def animate_to(self, index: int):
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        if self.reduce_motion:
            self.setCurrentIndex(index)
            return
        direction = 1 if index > self.currentIndex() else -1
        widget = self.widget(index)
        self.setCurrentIndex(index)
        base = widget.pos()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        widget.move(base + QPoint(direction * 10, 0))

        fade = QPropertyAnimation(effect, b"opacity", widget)
        fade.setDuration(160)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide = QPropertyAnimation(widget, b"pos", widget)
        slide.setDuration(160)
        slide.setStartValue(base + QPoint(direction * 10, 0))
        slide.setEndValue(base)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        group = QParallelAnimationGroup(widget)
        group.addAnimation(fade)
        group.addAnimation(slide)

        def finish():
            widget.move(base)
            widget.setGraphicsEffect(None)
            self._animation = None

        group.finished.connect(finish)
        self._animation = group
        group.start()


class SlidingTabBar(QWidget):
    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setFixedSize(488, 38)
        self.current_index = 0
        self.indicator = QFrame(self)
        self.indicator.setObjectName("tabIndicator")
        self.buttons = []
        self._animation = None
        self.reduce_motion = False
        for index, label in enumerate(labels):
            button = QPushButton(label, self)
            button.setObjectName("animatedTabButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, value=index: self.set_index(value, emit=True))
            self.buttons.append(button)
        self.indicator.lower()

    def resizeEvent(self, event):
        width = self.width() // max(1, len(self.buttons))
        for index, button in enumerate(self.buttons):
            button.setGeometry(index * width, 0, width, self.height())
        if self._animation is None:
            self.indicator.setGeometry(self._indicator_rect(self.current_index))
        super().resizeEvent(event)

    def _indicator_rect(self, index):
        width = self.width() // max(1, len(self.buttons))
        return QRect(index * width + 3, 3, width - 6, self.height() - 6)

    def set_index(self, index, emit=False):
        if not 0 <= index < len(self.buttons):
            return
        changed = index != self.current_index
        self.current_index = index
        for button_index, button in enumerate(self.buttons):
            button.setChecked(button_index == index)
        if changed and self.isVisible() and not self.reduce_motion:
            animation = QPropertyAnimation(self.indicator, b"geometry", self)
            animation.setDuration(180)
            animation.setStartValue(self.indicator.geometry())
            animation.setEndValue(self._indicator_rect(index))
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(lambda: setattr(self, "_animation", None))
            self._animation = animation
            animation.start()
        else:
            self.indicator.setGeometry(self._indicator_rect(index))
        if emit and changed:
            self.changed.emit(index)


class DashboardWidget(QWidget):
    open_settings = Signal()
    data_updated = Signal(object)

    def __init__(self, parent=None, settings_manager=None, translation_manager=None, theme_manager=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        self.current_scope = RuntimeScope.CODEX
        self.current_model_scope = settings_manager.get_model_scope() if settings_manager else "all"
        self.data = MultiRuntimeUsageSnapshot()
        self._refresh_thread = None
        self._refresh_worker = None
        self._silent_refresh = False

        self.setObjectName("dashboard")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)
        root.addLayout(self._build_header())
        root.addWidget(self._build_summary())
        root.addWidget(self._build_tab_area(), 1)

        if self.translation_manager:
            self.translation_manager.add_listener(self.update_text)
        if self.settings_manager:
            self.settings_manager.add_listener(self._on_settings_changed)
        self.update_text()
        self._on_settings_changed()

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(8)
        logo = QLabel()
        logo.setFixedSize(38, 38)
        logo_path = Path(__file__).resolve().parents[2] / "resources" / "icons" / "codexu-logo.svg"
        logo.setPixmap(QPixmap(str(logo_path)).scaled(
            36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        header.addWidget(logo)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel("CodexUU")
        name.setObjectName("brandName")
        brand.addWidget(name)
        header.addLayout(brand)
        header.addStretch()

        model_scope_group = QFrame()
        model_scope_group.setObjectName("topControlGroup")
        model_scope_layout = QHBoxLayout(model_scope_group)
        model_scope_layout.setContentsMargins(2, 2, 2, 2)
        model_scope_layout.setSpacing(0)
        self.model_scope_group = QButtonGroup(self)
        self.model_scope_group.setExclusive(True)
        self.model_scope_buttons = {}
        self.provider_scope_button = ProviderScopeButton()
        self.provider_scope_button.clicked.connect(lambda checked=False: self._set_model_scope("provider"))
        self.model_scope_group.addButton(self.provider_scope_button)
        self.model_scope_buttons["provider"] = self.provider_scope_button
        model_scope_layout.addWidget(self.provider_scope_button)
        for value, text, width in (("gpt", "GPT", 42), ("all", "全部", 46)):
            button = QPushButton(text)
            button.setObjectName("topToggleButton")
            button.setCheckable(True)
            button.setFixedSize(width, 28)
            button.clicked.connect(lambda checked=False, scope=value: self._set_model_scope(scope))
            self.model_scope_group.addButton(button)
            self.model_scope_buttons[value] = button
            model_scope_layout.addWidget(button)
        current_model_scope = self.settings_manager.get_model_scope() if self.settings_manager else "all"
        self.model_scope_buttons.get(current_model_scope, self.model_scope_buttons["all"]).setChecked(True)
        header.addWidget(model_scope_group)

        theme_group = QFrame()
        theme_group.setObjectName("topControlGroup")
        theme_layout = QHBoxLayout(theme_group)
        theme_layout.setContentsMargins(2, 2, 2, 2)
        theme_layout.setSpacing(0)
        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_buttons = {}
        for value, icon, tooltip in (
            ("auto", "theme-auto.svg", "跟随系统"),
            ("light", "theme-light.svg", "浅色"),
            ("dark", "theme-dark.svg", "深色"),
        ):
            button = QPushButton()
            button.setIcon(QIcon(icon_path(icon)))
            button.setIconSize(QSize(15, 15))
            button.setObjectName("topToggleButton")
            button.setCheckable(True)
            button.setFixedSize(28, 28)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, mode=value: self._set_theme(mode))
            self.theme_group.addButton(button)
            self.theme_buttons[value] = button
            theme_layout.addWidget(button)
        current_theme = self.theme_manager.get_theme() if self.theme_manager else "dark"
        self.theme_buttons.get(current_theme, self.theme_buttons["dark"]).setChecked(True)
        header.addWidget(theme_group)

        language_group = QFrame()
        language_group.setObjectName("topControlGroup")
        language_layout = QHBoxLayout(language_group)
        language_layout.setContentsMargins(2, 2, 2, 2)
        language_layout.setSpacing(0)
        self.language_group = QButtonGroup(self)
        self.language_group.setExclusive(True)
        self.language_buttons = {}
        for value, text in (("zh", "中"), ("en", "EN")):
            button = QPushButton(text)
            button.setObjectName("topToggleButton")
            button.setCheckable(True)
            button.setFixedSize(36, 28)
            button.clicked.connect(lambda checked=False, lang=value: self._set_language(lang))
            self.language_group.addButton(button)
            self.language_buttons[value] = button
            language_layout.addWidget(button)
        language = self.translation_manager.get_language() if self.translation_manager else "zh"
        self.language_buttons[language].setChecked(True)
        header.addWidget(language_group)

        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(QIcon(icon_path("refresh.svg")))
        self.refresh_button.setIconSize(QSize(16, 16))
        self.refresh_button.setObjectName("iconButton")
        self.refresh_button.setToolTip("刷新")
        self.refresh_button.setFixedSize(34, 34)
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon(icon_path("settings.svg")))
        self.settings_button.setIconSize(QSize(16, 16))
        self.settings_button.setObjectName("iconButton")
        self.settings_button.setToolTip("打开设置")
        self.settings_button.setFixedSize(34, 34)
        self.settings_button.clicked.connect(self.open_settings.emit)
        header.addWidget(self.settings_button)
        return header

    def _build_summary(self):
        summary = QFrame()
        summary.setObjectName("summaryPanel")
        summary.setFixedHeight(282)
        layout = QHBoxLayout(summary)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.quota_card = QuotaPanel()
        self.quota_card.mode_changed.connect(self._set_quota_display)
        if self.settings_manager:
            self.quota_card.set_display_mode(self.settings_manager.get_quota_display())
        layout.addWidget(self.quota_card)

        right = QVBoxLayout()
        right.setSpacing(10)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.today_card = MetricCard("今日", "metric-today.svg")
        self.week_card = MetricCard("本周", "metric-week.svg")
        self.month_card = MetricCard("本月", "metric-month.svg")
        self.cumulative_card = MetricCard("累计", "metric-all.svg")
        for card, mode in (
            (self.today_card, "daily"),
            (self.week_card, "weekly"),
            (self.month_card, "monthly"),
            (self.cumulative_card, "cumulative"),
        ):
            card.activated.connect(lambda value=mode: self._open_usage_mode(value))
            card.setToolTip("点击查看对应 Token 用量")
        cards.addWidget(self.today_card, 1)
        cards.addWidget(self.week_card, 1)
        cards.addWidget(self.month_card, 1)
        cards.addWidget(self.cumulative_card, 1)
        right.addLayout(cards, 1)
        self.value_card = ValueCard()
        right.addWidget(self.value_card)
        layout.addLayout(right, 1)
        return summary

    def _build_tab_area(self):
        panel = QFrame()
        panel.setObjectName("tabPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.tab_bar = SlidingTabBar(("今日任务", "用量趋势", "项目排行", "Skill"))
        for button, icon in zip(
            self.tab_bar.buttons,
            ("tab-today.svg", "tab-trend.svg", "tab-project.svg", "tab-skill.svg"),
        ):
            button.setIcon(QIcon(icon_path(icon)))
            button.setIconSize(QSize(15, 15))
        self.tab_bar.changed.connect(self._show_tab)
        self.tab_buttons = self.tab_bar.buttons
        tab_row.addWidget(self.tab_bar)
        tab_row.addStretch()
        self.tab_summary = QLabel("0 事项")
        self.tab_summary.setObjectName("metricLabel")
        tab_row.addWidget(self.tab_summary)
        layout.addLayout(tab_row)

        self.stack = AnimatedStackedWidget()
        self.task_tab = TaskBoardWidget()
        self.trend_tab = UsageTrendWidget(settings_manager=self.settings_manager)
        self.project_tab = ProjectRankingWidget()
        self.skill_tab = SkillUsageWidget()
        for widget in (self.task_tab, self.trend_tab, self.project_tab, self.skill_tab):
            self.stack.addWidget(widget)
        layout.addWidget(self.stack, 1)
        return panel

    def _show_tab(self, index):
        self.tab_bar.set_index(index)
        self.stack.animate_to(index)
        self._update_tab_summary()

    def _open_usage_mode(self, mode):
        self.trend_tab.set_mode(mode)
        self._show_tab(1)

    def _set_theme(self, theme):
        if self.theme_manager:
            self.theme_manager.set_theme(theme)
            self.theme_manager.apply_theme(QApplication.instance())
        if self.settings_manager:
            self.settings_manager.set_theme(theme)
            self.settings_manager.save()

    def _set_language(self, language):
        if self.translation_manager:
            self.translation_manager.set_language(language)
        if self.settings_manager:
            self.settings_manager.set_language(language)
            self.settings_manager.save()

    def _set_quota_display(self, mode):
        if self.settings_manager:
            self.settings_manager.set_quota_display(mode)
            self.settings_manager.save()

    def _provider_snapshot(self):
        snapshot = self.data.ccswitch
        return snapshot if snapshot is not None and snapshot.provider_name else None

    def _sync_provider_scope_button(self):
        snapshot = self.data.ccswitch
        self.provider_scope_button.set_snapshot(snapshot)
        if snapshot is None or not snapshot.provider_name:
            if self.current_model_scope == "provider":
                self.model_scope_buttons["all"].setChecked(True)
        else:
            self.model_scope_buttons["provider"].setChecked(self.current_model_scope == "provider")

    def _set_model_scope(self, scope):
        if scope == "provider" and self._provider_snapshot() is None:
            self.model_scope_buttons["all"].setChecked(True)
            return
        if self.settings_manager:
            self.settings_manager.set_model_scope(scope)
            self.settings_manager.save()
        else:
            self.current_model_scope = scope
            self._update()

    def _on_settings_changed(self):
        if not self.settings_manager:
            return
        model_scope = self.settings_manager.get_model_scope()
        if model_scope != self.current_model_scope:
            self.current_model_scope = model_scope
            self._update()
        self._sync_provider_scope_button()
        theme = self.settings_manager.get_theme()
        if theme in self.theme_buttons:
            self.theme_buttons[theme].setChecked(True)
        if model_scope in self.model_scope_buttons and not (model_scope == "provider" and self._provider_snapshot() is None):
            self.model_scope_buttons[model_scope].setChecked(True)
        self.quota_card.set_display_mode(self.settings_manager.get_quota_display())
        reduce_motion = self.settings_manager.get_reduce_motion()
        self.stack.set_reduce_motion(reduce_motion)
        self.tab_bar.reduce_motion = reduce_motion
        self.trend_tab.set_reduce_motion(reduce_motion)
        for card in (self.today_card, self.week_card, self.month_card, self.cumulative_card):
            card.set_reduce_motion(reduce_motion)
        self.value_card.set_reduce_motion(reduce_motion)

    def _tr(self, key, fallback):
        return self.translation_manager.tr(key) if self.translation_manager else fallback

    def update_text(self):
        english = bool(self.translation_manager and self.translation_manager.get_language() == "en")
        self.provider_scope_button.set_language("en" if english else "zh")
        self.model_scope_buttons["gpt"].setText("GPT")
        self.model_scope_buttons["all"].setText("All" if english else "全部")
        scope_tip = (
            "Switch token cards, trends and model usage between GPT-only and all models"
            if english else "切换顶部指标、用量趋势和模型统计：仅 GPT / 包含第三方模型"
        )
        for value, button in self.model_scope_buttons.items():
            if value == "provider":
                continue
            button.setToolTip(scope_tip)
        self.language_buttons["en" if english else "zh"].setChecked(True)
        self.quota_card.title.setText("Quota usage" if english else "额度使用情况")
        self.today_card.title.setText("Today" if english else "今日")
        self.week_card.title.setText("This week" if english else "本周")
        self.month_card.title.setText("This month" if english else "本月")
        self.cumulative_card.title.setText("All time" if english else "累计")
        self.value_card.title.setText("Value progress" if english else "羊毛进度")
        for card in (
            self.quota_card, self.today_card, self.week_card, self.month_card,
            self.cumulative_card, self.value_card,
        ):
            if hasattr(card, "set_language"):
                card.set_language("en" if english else "zh")
        labels = ("Today", "Trends", "Projects", "Skills") if english else ("今日任务", "用量趋势", "项目排行", "Skill")
        for button, label in zip(self.tab_buttons, labels):
            button.setText(label)
        for widget in (self.task_tab, self.trend_tab, self.project_tab, self.skill_tab):
            if hasattr(widget, "set_language"):
                widget.set_language("en" if english else "zh")

    def refresh(self, silent=False):
        QTimer.singleShot(0, lambda: self._do_refresh(silent))

    def shutdown(self):
        """Wait for an in-flight refresh before Qt destroys its worker thread."""
        thread = self._refresh_thread
        if thread is None:
            return
        if thread.isRunning():
            thread.quit()
            if not thread.wait(20000):
                thread.terminate()
                thread.wait(1000)
        self._refresh_thread = None
        self._refresh_worker = None

    def _do_refresh(self, silent=False):
        if self._refresh_thread is not None:
            return
        self._silent_refresh = bool(silent)
        if not self._silent_refresh:
            self.refresh_button.setEnabled(False)
            self.refresh_button.setIcon(QIcon())
            self.refresh_button.setText("…")
            self.refresh_button.setToolTip("Refreshing…" if self._is_english() else "正在刷新…")
        thread = QThread(self)
        worker = RefreshWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_refresh_loaded)
        worker.failed.connect(self._on_refresh_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_refresh_worker)
        self._refresh_thread = thread
        self._refresh_worker = worker
        thread.start()

    def _on_refresh_loaded(self, result):
        codex, tasks, daily, projects, tools, skills, models, ccswitch = result
        self.data.codex = codex
        self.data.ccswitch = ccswitch
        self.data.tasks = tasks
        self.data.daily_tokens = sorted(daily, key=lambda item: item.date, reverse=True)
        self.data.projects = sorted(projects, key=lambda item: item.token_total, reverse=True)
        self.data.tools = tools
        self.data.skills = skills
        self.data.models = models
        if not self._silent_refresh:
            self.refresh_button.setEnabled(True)
            self._restore_refresh_button()
        self._update()
        now = datetime.now().strftime("%H:%M:%S")
        self.refresh_button.setToolTip(f"Updated at {now}" if self._is_english() else f"刷新完成 · {now}")

    def _on_refresh_failed(self, error):
        if not self._silent_refresh:
            self.refresh_button.setEnabled(True)
            self._restore_refresh_button()
        self.refresh_button.setToolTip(f"Refresh failed: {error}" if self._is_english() else f"刷新失败：{error}")

    def _clear_refresh_worker(self):
        self._refresh_thread = None
        self._refresh_worker = None

    def _restore_refresh_button(self):
        self.refresh_button.setText("")
        self.refresh_button.setIcon(QIcon(icon_path("refresh.svg")))
        self.refresh_button.setIconSize(QSize(16, 16))

    def _is_english(self):
        return bool(self.translation_manager and self.translation_manager.get_language() == "en")

    def _visible_data(self):
        scope = self.current_scope
        return (
            [item for item in self.data.tasks if item.runtime == scope],
            [item for item in self.data.daily_tokens if item.runtime == scope],
            [item for item in self.data.projects if item.runtime == scope],
            [item for item in self.data.tools if item.runtime == scope],
            [item for item in self.data.skills if item.runtime == scope],
        )

    def _update_tab_summary(self):
        tasks, daily, projects, tools, skills = self._visible_data()
        index = self.stack.currentIndex()
        english = bool(self.translation_manager and self.translation_manager.get_language() == "en")
        summaries = (
            f"{self.task_tab.project_count()} projects" if english else f"{self.task_tab.project_count()} 个项目",
            f"{len(daily)} active days" if english else f"{len(daily)} 活跃日",
            f"{len(projects)} projects" if english else f"{len(projects)} 项目",
            f"{len(skills)} skills · {len(tools)} calls" if english else f"{len(skills)} Skill · {len(tools)} 次调用",
        )
        self.tab_summary.setText(summaries[index])

    def _update(self):
        snapshot = self.data.codex
        self._sync_provider_scope_button()
        provider = self._provider_snapshot() if self.current_model_scope == "provider" else None
        if provider is not None:
            self.quota_card.update_provider(provider)
        else:
            self.quota_card.update_quota(
                snapshot.quota_5h,
                snapshot.quota_7d,
                snapshot.quota_status,
                snapshot.quota_month,
            )
        tasks, daily, projects, tools, skills = self._visible_data()
        self.task_tab.update_tasks(tasks)
        models = [item for item in self.data.models if item.runtime == self.current_scope]
        model_scope = self.current_model_scope
        if provider is not None:
            periods = provider.tokens
            daily = provider.daily_tokens
            cumulative_total = periods.cumulative.total
            self.today_card.update_value(periods.today, provider.today_cost_usd)
            self.week_card.update_value(periods.current_week, provider.current_week_cost_usd)
            self.month_card.update_value(periods.current_month, provider.current_month_cost_usd)
            self.cumulative_card.update_value(periods.cumulative, provider.total_cost_usd)
            self.value_card.update_provider(provider)
            models = []
        elif model_scope == "gpt":
            models = [item for item in models if is_gpt_model(item.name)]
            scoped = _model_scope_summary(models, self.current_scope)
            periods = scoped["periods"]
            values = scoped["values"]
            daily = scoped["daily"]
            cumulative_total = periods["cumulative"].total
            self.today_card.update_value(periods["today"], values["today"])
            self.week_card.update_value(periods["week"], values["week"])
            self.month_card.update_value(periods["month"], values["month"])
            self.cumulative_card.update_value(periods["cumulative"], values["cumulative"])
            self.value_card.update_value(values["month"], scoped["month_coverage"], scoped["month_unpriced"])
        else:
            cumulative_total = snapshot.cumulative_index_total or snapshot.tokens.cumulative.total
            self.today_card.update_value(snapshot.tokens.today, snapshot.today_api_equivalent_value)
            self.week_card.update_value(snapshot.tokens.current_week, snapshot.current_week_api_equivalent_value)
            self.month_card.update_value(snapshot.tokens.current_month, snapshot.monthly_api_equivalent_value)
            self.cumulative_card.update_value(
                snapshot.tokens.cumulative,
                snapshot.api_equivalent_value,
                snapshot.cumulative_index_total,
            )
            self.value_card.update_value(
                snapshot.monthly_api_equivalent_value,
                snapshot.pricing_coverage_pct,
                snapshot.unpriced_token_total,
            )
        self.trend_tab.set_data(
            daily,
            cumulative_total,
            models,
        )
        self.project_tab.update_projects(projects)
        self.skill_tab.set_data(skills, tools)
        self._update_tab_summary()
        self.data_updated.emit(self.data)
