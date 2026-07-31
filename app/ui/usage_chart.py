from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.data.models import (
    DailyToken,
    ModelUsage,
    RuntimeScope,
    TokenBreakdown,
    estimate_model_api_value,
    format_tokens,
    pricing_source_for_model,
    prices_for_model,
)
from app.ui.heatmap import TokenHeatmap
from app.utils.statistics_timezone import get_statistics_timezone


MODES = ("daily", "weekly", "monthly", "cumulative")
MODEL_ACTIVITY_WINDOWS = (30, 60, 90, 180)
MODEL_METRICS = ("tokens", "api")
OTHER_MODEL_KEY = "__other_models__"
ICONS_DIR = Path(__file__).resolve().parents[2] / "resources" / "icons"


def _header_icon(name):
    icon = QLabel()
    icon.setFixedSize(16, 16)
    icon.setPixmap(QPixmap(str(ICONS_DIR / name)).scaled(
        16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
    ))
    return icon


def _item_date(item) -> date:
    return item.date.date() if hasattr(item.date, "date") else item.date


def _month_shift(day: date, delta: int) -> date:
    month_index = day.year * 12 + day.month - 1 + delta
    return date(month_index // 12, month_index % 12 + 1, 1)


def period_start(mode: str, today: date | None = None) -> date | None:
    today = today or get_statistics_timezone().now_date()
    if mode == "daily":
        return today - timedelta(days=29)
    if mode == "weekly":
        return today - timedelta(days=today.weekday(), weeks=11)
    if mode == "monthly":
        return _month_shift(today.replace(day=1), -11)
    return None


def period_label(mode: str, english: bool) -> str:
    values = {
        "daily": ("近 30 天", "Last 30 days"),
        "weekly": ("近 12 周", "Last 12 weeks"),
        "monthly": ("近 12 个月", "Last 12 months"),
        "cumulative": ("累计", "All time"),
    }
    return values[mode][1 if english else 0]


def model_period_start(mode: str, today: date | None = None) -> date | None:
    """Model lists use the active calendar period, not the 30-day trend window."""
    today = today or get_statistics_timezone().now_date()
    return today if mode == "daily" else period_start(mode, today)


def model_period_label(mode: str, english: bool, today: date | None = None) -> str:
    today = today or get_statistics_timezone().now_date()
    if mode == "daily":
        return f"Today {today:%m/%d}" if english else f"本日 {today:%m/%d}"
    if mode == "weekly":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return f"This week {start:%m/%d}–{end:%m/%d}" if english else f"本周 {start:%m/%d}–{end:%m/%d}"
    if mode == "monthly":
        end = today.replace(day=monthrange(today.year, today.month)[1])
        return f"This month {today:%m/%d}–{end:%m/%d}" if english else f"本月 {today:%m/%d}–{end:%m/%d}"
    return "All time" if english else "累计"


def period_range_text(mode: str, english: bool, today: date | None = None) -> str:
    """Scheme B range-strip value without redundant 本日/本周 prefixes."""
    today = today or get_statistics_timezone().now_date()
    if mode == "daily":
        return f"{today:%m/%d}"
    if mode == "weekly":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return f"{start:%m/%d}-{end:%m/%d}"
    if mode == "monthly":
        start = today.replace(day=1)
        end = today.replace(day=monthrange(today.year, today.month)[1])
        return f"{start:%m/%d}-{end:%m/%d}"
    return "All records" if english else "全部记录"


def model_activity_start(days: int, today: date | None = None) -> date:
    """Return the inclusive start of a model activity window."""
    today = today or get_statistics_timezone().now_date()
    days = max(1, int(days))
    return today - timedelta(days=days - 1)


def model_activity_range_text(days: int, english: bool, today: date | None = None) -> str:
    today = today or get_statistics_timezone().now_date()
    start = model_activity_start(days, today)
    return f"{start:%Y/%m/%d} - {today:%Y/%m/%d}"


def format_metric_value(value: float, metric: str, english: bool = False) -> str:
    if metric == "api":
        return f"${float(value):,.2f}"
    return format_tokens(int(round(value)))


def _exact_model_api_value(tokens: TokenBreakdown, model: str) -> float:
    prices = prices_for_model(model)
    if not prices:
        return 0.0
    return (
        tokens.uncached_input / 1_000_000 * prices["uncached_input"]
        + tokens.cached_input / 1_000_000 * prices["cached_input"]
        + tokens.output / 1_000_000 * prices["output"]
    )


def _daily_metric_points(model: ModelUsage, days: int, metric: str, today: date | None = None):
    """Build a zero-filled model series without changing source model data."""
    today = today or get_statistics_timezone().now_date()
    start = model_activity_start(days, today)
    by_day = defaultdict(float)
    prices_available = prices_for_model(model.name) is not None
    for item in model.daily_tokens or []:
        day = _item_date(item)
        if day < start or day > today:
            continue
        if metric == "tokens":
            amount = item.total
        elif prices_available:
            amount = _exact_model_api_value(
                TokenBreakdown(
                    cached_input=item.cached_input,
                    uncached_input=item.uncached_input,
                    output=item.output,
                ),
                model.name,
            ) or 0.0
        else:
            amount = 0.0
        by_day[day] += amount
    return [
        ((start + timedelta(days=index)).strftime("%m/%d"), by_day[start + timedelta(days=index)])
        for index in range(max(1, int(days)))
    ]


def _in_period(value: datetime | None, start: date | None, end: date) -> bool:
    if value is None:
        return False
    day = get_statistics_timezone().date_for(value) if hasattr(value, "tzinfo") else value
    return day <= end and (start is None or day >= start)


def aggregate_points(daily_tokens, mode: str, cumulative_total=None):
    ordered = sorted(daily_tokens or [], key=_item_date)
    totals_by_day = defaultdict(int)
    for item in ordered:
        totals_by_day[_item_date(item)] += item.total
    today = get_statistics_timezone().now_date()
    if mode == "daily":
        start = today - timedelta(days=29)
        return [
            ((start + timedelta(days=index)).strftime("%m/%d"), totals_by_day[start + timedelta(days=index)])
            for index in range(30)
        ]

    buckets = defaultdict(int)
    for item in ordered:
        day = _item_date(item)
        if mode == "weekly":
            start = day - timedelta(days=day.weekday())
            key = start
        else:
            key = day.replace(day=1)
        buckets[key] += item.total
    if mode == "weekly":
        current = today - timedelta(days=today.weekday())
        starts = [current - timedelta(weeks=index) for index in range(11, -1, -1)]
        return [(start.strftime("%m/%d"), buckets[start]) for start in starts]
    if mode == "monthly":
        starts = [_month_shift(today.replace(day=1), index) for index in range(-11, 1)]
        return [(f"{start.month:02d}月", buckets[start]) for start in starts]

    starts = sorted(buckets)
    known_total = sum(buckets.values())
    running = max(0, int(cumulative_total or 0) - known_total)
    result = []
    for start in starts:
        running += buckets[start]
        result.append((f"{start.month:02d}月", running))
    return result[-12:]


class StatStrip(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(0)
        self.items = []
        for index in range(4):
            box = QVBoxLayout()
            box.setSpacing(1)
            value = QLabel("0")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet("font-size: 14px; font-weight: 700;")
            label = QLabel("")
            label.setObjectName("caption")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(value)
            box.addWidget(label)
            layout.addLayout(box, 1)
            self.items.append((value, label))
            if index < 3:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.VLine)
                divider.setObjectName("statDivider")
                layout.addWidget(divider)

    def set_data(self, daily_tokens, english=False, cumulative_total=None):
        by_day = {_item_date(item): item.total for item in daily_tokens or []}
        total = cumulative_total if cumulative_total is not None else sum(by_day.values())
        peak = max(by_day.values(), default=0)
        active = sum(1 for value in by_day.values() if value > 0)
        streak = longest_streak(by_day)
        values = (format_tokens(total), format_tokens(peak), str(active), str(streak))
        labels = (
            ("All-time tokens", "Peak day", "Active days", "Longest streak")
            if english else ("累计 Token", "单日峰值", "活跃天数", "最长连续天数")
        )
        for (value_label, label), value, text in zip(self.items, values, labels):
            value_label.setText(value)
            label.setText(text)


def longest_streak(by_day):
    days = sorted(day for day, value in by_day.items() if value > 0)
    best = current = 0
    previous = None
    for day in days:
        current = current + 1 if previous and day == previous + timedelta(days=1) else 1
        best = max(best, current)
        previous = day
    return best


def _model_label(name: str, english: bool = False) -> str:
    value = (name or "unknown").strip()
    aliases = {
        "gpt-5.6-sol": "Sol",
        "gpt-5.6-terra": "Terra",
        "gpt-5.6-luna": "Luna",
        OTHER_MODEL_KEY: "Other models" if english else "其他模型",
    }
    return aliases.get(value.lower(), value)


def _effort_label(effort: str, english: bool) -> str:
    key = (effort or "").strip().lower()
    zh = {"low": "低", "medium": "中", "high": "高", "xhigh": "超高", "max": "极高", "ultra": "极限"}
    en = {"low": "Low", "medium": "Medium", "high": "High", "xhigh": "X-high", "max": "Max", "ultra": "Ultra"}
    return (en if english else zh).get(key, "Not provided" if english else "未提供")


def _model_key(model: ModelUsage) -> str:
    return f"{model.name}\x1f{model.effort}"


def _api_value_text(model: ModelUsage, english: bool) -> str:
    if model.pricing_coverage_pct <= 0:
        return "Unpriced" if english else "未计价"
    prefix = "~" if model.pricing_coverage_pct < 99.5 else ""
    value = f"{prefix}${model.estimated_value:,.2f}"
    if model.pricing_coverage_pct < 99.5:
        value += f" ({model.pricing_coverage_pct:.0f}%)"
    return value


class ModelUsageRow(QFrame):
    activated = Signal(object)

    def __init__(
        self,
        model: ModelUsage,
        total: int,
        english: bool,
        period_text: str,
        metric: str = "tokens",
        parent=None,
    ):
        super().__init__(parent)
        self.model = model
        self.setObjectName("modelUsageRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 7, 11, 7)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        model_name = _model_label(model.name, english)
        effort = _effort_label(model.effort, english) if model.effort else ""
        name = QLabel(f"{model_name} · {effort}" if effort else model_name)
        name.setObjectName("modelUsageName")
        name.setToolTip(model.name)
        heading.addWidget(name)
        heading.addStretch()
        value = QLabel(
            format_tokens(model.token_total)
            if metric == "tokens" else _api_value_text(model, english)
        )
        value.setObjectName("modelUsageValue")
        heading.addWidget(value)
        layout.addLayout(heading)
        progress = QProgressBar()
        progress.setObjectName("modelUsageProgress")
        progress.setRange(0, 1000)
        progress.setValue(round(model.token_total / max(1, total) * 1000))
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        layout.addWidget(progress)
        detail = QLabel(
            f"{period_text} · {model.session_count} sessions · {model.turn_count} turns"
            if english else f"{period_text} · {model.session_count} 个会话 · {model.turn_count} 个回合"
        )
        detail.setObjectName("metricHint")
        layout.addWidget(detail)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.model)
        super().mouseReleaseEvent(event)


class UsagePlot(QWidget):
    LEFT_MARGIN = 54
    TOP_MARGIN = 6
    RIGHT_MARGIN = 18
    BOTTOM_MARGIN = 32

    def __init__(self, bars=False, parent=None):
        super().__init__(parent)
        self.bars = bars
        self.points = []
        self.series = []
        self.baseline = []
        self.value_metric = "tokens"
        self.english = False
        self.hover_index = -1
        # The dashboard gives overview and model plots different live heights.
        # A large minimum makes the stacked page taller than its viewport and
        # silently clips the zero baseline and X-axis labels.
        self.setMinimumHeight(48)
        self.setMouseTracking(True)

    def set_points(self, points, metric="tokens", english=False):
        self.points = list(points or [])
        self.series = []
        self.baseline = []
        self.value_metric = metric
        self.english = english
        self.hover_index = -1
        self.update()

    def set_series(self, series, baseline=None, metric="tokens", english=False):
        self.series = [
            (str(name), list(points or []))
            for name, points in (series or [])
            if points
        ]
        self.baseline = list(baseline or [])
        self.points = self.baseline or (self.series[0][1] if self.series else [])
        self.value_metric = metric
        self.english = english
        self.hover_index = -1
        self.update()

    def mouseMoveEvent(self, event):
        if not self.points:
            return
        left, right = self.LEFT_MARGIN, self.RIGHT_MARGIN
        width = max(1, self.width() - left - right)
        index = round((event.position().x() - left) / width * max(1, len(self.points) - 1))
        self.hover_index = max(0, min(len(self.points) - 1, index))
        label, _value = self.points[self.hover_index]
        if self.series:
            values = []
            if self.baseline:
                values.append(
                    f"{'Total' if self.english else '总量'}: "
                    f"{format_metric_value(self.baseline[self.hover_index][1], self.value_metric, self.english)}"
                )
            values.extend(
                f"{name}: {format_metric_value(points[self.hover_index][1], self.value_metric, self.english)}"
                for name, points in self.series
                if self.hover_index < len(points)
            )
            tooltip_text = f"{label}\n" + "\n".join(values)
        else:
            value = self.points[self.hover_index][1]
            unit = "API value" if self.value_metric == "api" else "token"
            tooltip_text = f"{label}\n{format_metric_value(value, self.value_metric, self.english)} {unit}"
        # Always open above the cursor so a point on the zero baseline cannot
        # push the tooltip underneath the card/window boundary.
        tooltip_pos = event.globalPosition().toPoint() + QPoint(12, -54)
        QToolTip.showText(tooltip_pos, tooltip_text, self)
        self.update()

    def leaveEvent(self, event):
        self.hover_index = -1
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.points:
            painter.setPen(QColor("#8a94a6"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "—")
            return
        left, top, right, bottom = (
            self.LEFT_MARGIN, self.TOP_MARGIN, self.RIGHT_MARGIN, self.BOTTOM_MARGIN,
        )
        width = max(1, self.width() - left - right)
        height = max(1, self.height() - top - bottom)
        baseline = top + height
        self._last_plot_rect = QRectF(left, top, width, height)
        self._last_y_axis_label_rects = []
        self._last_x_axis_label_rects = []
        self._last_axis_label_rects = []
        all_values = [value for _, value in self.points]
        for _name, series in self.series:
            all_values.extend(value for _, value in series)
        maximum = max(all_values or [0]) or 1
        painter.setFont(QFont("Microsoft YaHei", 8))
        # Short model cards cannot fit three 14px Y labels without collisions.
        # Keep the zero baseline mandatory, then add max/mid only when the live
        # plot height can actually accommodate them.
        y_ticks = (0, 0.5, 1) if height >= 58 else ((0, 1) if height >= 32 else (0,))
        for pct in y_ticks:
            y = top + height * (1 - pct)
            painter.setPen(QPen(QColor(127, 145, 172, 36), 1))
            painter.drawLine(left, int(y), self.width() - right, int(y))
            painter.setPen(QColor("#8a94a6"))
            label_y = y - 14 if pct == 0 else (top if pct == 1 else y - 7)
            label_rect = QRectF(0, label_y, left - 8, 14)
            self._last_y_axis_label_rects.append(label_rect)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_metric_value(maximum * pct, self.value_metric, self.english),
            )

        count = len(self.points)

        def point_coords(points):
            coords = []
            for index, (_, value) in enumerate(points):
                x = left + width * (index + (0.5 if self.bars else 0)) / (count if self.bars else max(1, count - 1))
                y = top + height * (1 - value / maximum)
                coords.append(QPointF(x, y))
            return coords

        coords = point_coords(self.points)
        if self.series:
            baseline_coords = point_coords(self.baseline) if self.baseline else []
            if baseline_coords:
                painter.setPen(QPen(QColor("#93a0b5"), 1, Qt.PenStyle.DashLine))
                painter.drawPolyline(baseline_coords)
            colors = ("#6d9dff", "#8d74ff", "#e99a25", "#55c6a5", "#e879a9")
            for index, (_name, points) in enumerate(self.series):
                series_coords = point_coords(points)
                color = colors[index % len(colors)]
                painter.setPen(QPen(QColor(color), 1.6))
                painter.drawPolyline(series_coords)
                if self.hover_index >= 0 and self.hover_index < len(series_coords):
                    point = series_coords[self.hover_index]
                    painter.setBrush(QColor("#ffffff"))
                    painter.setPen(QPen(QColor(color), 2))
                    painter.drawEllipse(point, 3.5, 3.5)
        elif self.bars:
            bar_width = max(5, min(22, width / max(1, count) * 0.55))
            for index, point in enumerate(coords):
                color = QColor("#6d9dff") if index != self.hover_index else QColor("#326ad6")
                painter.fillRect(QRectF(point.x() - bar_width / 2, point.y(), bar_width, baseline - point.y()), color)
        else:
            area = QPainterPath(coords[0])
            for point in coords[1:]:
                area.lineTo(point)
            area.lineTo(coords[-1].x(), baseline)
            area.lineTo(coords[0].x(), baseline)
            area.closeSubpath()
            painter.fillPath(area, QColor(78, 130, 227, 38))
            line = QPainterPath(coords[0])
            for point in coords[1:]:
                line.lineTo(point)
            painter.setPen(QPen(QColor("#6d9dff"), 2))
            painter.drawPath(line)
            for index, point in enumerate(coords):
                painter.setBrush(QColor("#ffffff") if index == self.hover_index else QColor("#6d9dff"))
                painter.setPen(QPen(QColor("#6d9dff"), 2))
                painter.drawEllipse(point, 4 if index == self.hover_index else 2.5, 4 if index == self.hover_index else 2.5)

        painter.setPen(QColor("#8a94a6"))
        month_labels = count <= 12 and all(label.endswith("月") for label, _ in self.points)
        step = 1 if month_labels else max(1, count // 6)
        for index, (label, _) in enumerate(self.points):
            if index not in (0, count - 1) and index % step:
                continue
            x = coords[index].x()
            label_width = 36.0 if month_labels else 64.0
            label_left = max(0.0, min(self.width() - label_width, x - label_width / 2))
            label_rect = QRectF(label_left, baseline + 8, label_width, 16)
            self._last_x_axis_label_rects.append(label_rect)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignCenter,
                label,
            )
        self._last_axis_label_rects = self._last_y_axis_label_rects + self._last_x_axis_label_rects


class UsageTrendWidget(QWidget):
    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.daily_tokens = []
        self.model_usage = []
        self.selected_model = None
        self.selected_model_key = None
        saved_window = (
            settings_manager.get_model_activity_window()
            if settings_manager and hasattr(settings_manager, "get_model_activity_window") else 30
        )
        saved_metric = (
            settings_manager.get_model_metric()
            if settings_manager and hasattr(settings_manager, "get_model_metric") else "tokens"
        )
        self.model_activity_window = saved_window if saved_window in MODEL_ACTIVITY_WINDOWS else 30
        self.model_metric = saved_metric if saved_metric in MODEL_METRICS else "tokens"
        self.cumulative_total = None
        self.mode = "daily"
        self.language = "zh"
        self.data_updated_at = datetime.now(timezone.utc)
        self._mode_animation = None
        self.reduce_motion = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.stats = StatStrip()
        layout.addWidget(self.stats)

        controls = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        for index, mode in enumerate(MODES):
            button = QPushButton("")
            button.setObjectName("miniTabButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, value=mode: self.set_mode(value))
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            controls.addWidget(button)
        controls.addStretch()
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.overview_button = QPushButton("")
        self.models_button = QPushButton("")
        for index, button in enumerate((self.overview_button, self.models_button)):
            button.setObjectName("miniTabButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            self.view_group.addButton(button, index)
            controls.addWidget(button)
        self.view_group.idClicked.connect(self._set_view)
        layout.addLayout(controls)

        self.range_strip = QFrame()
        self.range_strip.setObjectName("rangeStrip")
        self.range_strip.setFixedHeight(28)
        range_layout = QHBoxLayout(self.range_strip)
        range_layout.setContentsMargins(10, 3, 10, 3)
        range_layout.setSpacing(7)
        self.range_caption = QLabel("")
        self.range_caption.setObjectName("metricHint")
        range_layout.addWidget(self.range_caption)
        self.range_value = QLabel("")
        self.range_value.setObjectName("rangeValue")
        range_layout.addWidget(self.range_value)
        range_layout.addStretch()
        self.updated_label = QLabel("")
        self.updated_label.setObjectName("metricHint")
        range_layout.addWidget(self.updated_label)
        layout.addWidget(self.range_strip)

        self.charts_host = QWidget()
        charts = QHBoxLayout(self.charts_host)
        charts.setContentsMargins(0, 0, 0, 0)
        charts.setSpacing(10)
        left = QFrame()
        left.setObjectName("surfaceCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 8, 14, 8)
        left_header = QHBoxLayout()
        left_header.addWidget(_header_icon("activity.svg"))
        self.activity_title = QLabel("Token 活动")
        self.activity_title.setObjectName("sectionTitle")
        left_header.addWidget(self.activity_title)
        left_header.addStretch()
        left_layout.addLayout(left_header)
        self.activity_stack = QStackedWidget()
        self.heatmap = TokenHeatmap()
        self.bars = UsagePlot(bars=True)
        self.activity_stack.addWidget(self.heatmap)
        self.activity_stack.addWidget(self.bars)
        left_layout.addWidget(self.activity_stack, 1)
        charts.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("surfaceCard")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 8, 14, 8)
        trend_header = QHBoxLayout()
        trend_header.addWidget(_header_icon("tab-trend.svg"))
        self.trend_title = QLabel("趋势")
        self.trend_title.setObjectName("sectionTitle")
        trend_header.addWidget(self.trend_title)
        trend_header.addStretch()
        right_layout.addLayout(trend_header)
        self.chart = UsagePlot()
        right_layout.addWidget(self.chart, 1)
        charts.addWidget(right, 1)
        self.models_host = self._build_models_host()
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.charts_host)
        self.content_stack.addWidget(self.models_host)
        layout.addWidget(self.content_stack, 1)
        self.set_language("zh")

    def _build_models_host(self):
        host = QWidget()
        columns = QHBoxLayout(host)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(10)

        ranking = QFrame()
        ranking.setObjectName("surfaceCard")
        ranking_layout = QVBoxLayout(ranking)
        ranking_layout.setContentsMargins(14, 8, 14, 8)
        model_controls = QHBoxLayout()
        model_controls.setSpacing(2)
        self.models_title = QLabel("")
        self.models_title.setObjectName("sectionTitle")
        model_controls.addWidget(self.models_title)
        model_controls.addStretch()
        self.model_window_group = QButtonGroup(self)
        self.model_window_group.setExclusive(True)
        self.model_window_buttons = {}
        for days in MODEL_ACTIVITY_WINDOWS:
            button = QPushButton("")
            button.setObjectName("miniTabButton")
            button.setCheckable(True)
            button.setFixedWidth(42)
            button.clicked.connect(lambda checked=False, value=days: self.set_model_activity_window(value))
            self.model_window_group.addButton(button)
            self.model_window_buttons[days] = button
            model_controls.addWidget(button)
        self.model_metric_group = QButtonGroup(self)
        self.model_metric_group.setExclusive(True)
        self.model_metric_buttons = {}
        for metric in MODEL_METRICS:
            button = QPushButton("")
            button.setObjectName("miniTabButton")
            button.setCheckable(True)
            button.setFixedWidth(54)
            button.clicked.connect(lambda checked=False, value=metric: self.set_model_metric(value))
            self.model_metric_group.addButton(button)
            self.model_metric_buttons[metric] = button
            model_controls.addWidget(button)
        ranking_layout.addLayout(model_controls)
        self.models_scroll = QScrollArea()
        self.models_scroll.setWidgetResizable(True)
        self.models_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.models_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.models_list = QWidget()
        self.models_list_layout = QVBoxLayout(self.models_list)
        self.models_list_layout.setContentsMargins(0, 0, 0, 0)
        self.models_list_layout.setSpacing(7)
        self.models_list_layout.addStretch()
        self.models_scroll.setWidget(self.models_list)
        ranking_layout.addWidget(self.models_scroll, 1)
        columns.addWidget(ranking, 1)

        detail = QFrame()
        detail.setObjectName("surfaceCard")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(14, 8, 14, 8)
        detail_header = QHBoxLayout()
        self.model_detail_title = QLabel("")
        self.model_detail_title.setObjectName("sectionTitle")
        detail_header.addWidget(self.model_detail_title)
        detail_header.addStretch()
        self.model_detail_value = QLabel("")
        self.model_detail_value.setObjectName("modelUsageValue")
        detail_header.addWidget(self.model_detail_value)
        detail_layout.addLayout(detail_header)
        self.model_detail_meta = QLabel("")
        self.model_detail_meta.setObjectName("metricHint")
        self.model_detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.model_detail_meta)
        metrics = QHBoxLayout()
        metrics.setSpacing(7)
        self.model_metric_labels = []
        for object_name in ("uncachedMetric", "cachedMetric", "outputMetric"):
            tile = QFrame()
            tile.setObjectName("modelMetricTile")
            tile.setProperty("tone", object_name)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(9, 5, 9, 5)
            tile_layout.setSpacing(1)
            metric_value = QLabel("0")
            metric_value.setObjectName("modelMetricValue")
            metric_name = QLabel("")
            metric_name.setObjectName("metricHint")
            tile_layout.addWidget(metric_value)
            tile_layout.addWidget(metric_name)
            metrics.addWidget(tile, 1)
            self.model_metric_labels.append((metric_value, metric_name))
        detail_layout.addLayout(metrics)
        self.model_chart = UsagePlot()
        detail_layout.addWidget(self.model_chart, 1)
        columns.addWidget(detail, 1)
        return host

    def set_language(self, language):
        self.language = language
        english = language == "en"
        self.activity_title.setText("Token activity" if english else "Token 活动")
        self.overview_button.setText("Overview" if english else "概览")
        self.models_button.setText("Models" if english else "模型")
        self.models_title.setText("Model usage" if english else "模型使用量")
        for days, button in self.model_window_buttons.items():
            button.setText(f"{days}d" if english else f"{days}天")
            button.setToolTip(
                f"Model activity: {days} days" if english else f"模型活动范围：{days} 天"
            )
            button.setChecked(days == self.model_activity_window)
        metric_labels = {
            "tokens": "Tokens" if english else "Token",
            "api": "API" if english else "API费用",
        }
        for metric, button in self.model_metric_buttons.items():
            button.setText(metric_labels[metric])
            button.setToolTip(
                "Show token volume" if english and metric == "tokens" else
                "Show exact-model API equivalent value" if english else
                "显示 Token 数量" if metric == "tokens" else "显示按精确模型价格计算的 API 等效费用"
            )
            button.setChecked(metric == self.model_metric)
        self._render()

    def set_model_activity_window(self, days: int):
        try:
            days = int(days)
        except (TypeError, ValueError):
            return
        if days not in MODEL_ACTIVITY_WINDOWS or days == self.model_activity_window:
            return
        self.model_activity_window = days
        if self.settings_manager and hasattr(self.settings_manager, "set_model_activity_window"):
            self.settings_manager.set_model_activity_window(days)
            self.settings_manager.save()
        self.model_window_buttons[days].setChecked(True)
        self._render_models()

    def set_model_metric(self, metric: str):
        if metric not in MODEL_METRICS or metric == self.model_metric:
            return
        self.model_metric = metric
        if self.settings_manager and hasattr(self.settings_manager, "set_model_metric"):
            self.settings_manager.set_model_metric(metric)
            self.settings_manager.save()
        self.model_metric_buttons[metric].setChecked(True)
        self._render_models()

    def _update_period_controls(self):
        english = self.language == "en"
        labels = dict(zip(MODES, ("Daily", "Weekly", "Monthly", "Cumulative")
                          if english else ("每日", "每周", "每月", "累计")))
        today = get_statistics_timezone().now_date()
        for mode, button in self.mode_buttons.items():
            title = labels[mode]
            button.setText(title)
            button.setToolTip(f"{title} · {period_range_text(mode, english, today)}")
        self.range_caption.setText("Range" if english else "统计范围")
        self.range_value.setText(period_range_text(self.mode, english, today))
        updated = self.data_updated_at.astimezone(get_statistics_timezone().tzinfo())
        self.updated_label.setText(
            f"Data updated {updated:%m/%d %H:%M}" if english
            else f"数据更新 {updated:%m/%d %H:%M}"
        )
        self.updated_label.setToolTip(
            updated.strftime("%Y-%m-%d %H:%M:%S %Z")
        )

    def _set_view(self, index):
        self.content_stack.setCurrentIndex(index)

    def set_reduce_motion(self, enabled):
        self.reduce_motion = bool(enabled)

    def set_mode(self, mode):
        if mode not in MODES or mode == self.mode:
            return
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        self._update_period_controls()
        if not self.isVisible() or self.reduce_motion:
            self._render()
            return
        effect = QGraphicsOpacityEffect(self.charts_host)
        self.charts_host.setGraphicsEffect(effect)
        fade_out = QPropertyAnimation(effect, b"opacity", self)
        fade_out.setDuration(60)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.35)
        fade_out.setEasingCurve(QEasingCurve.Type.OutCubic)

        def swap_content():
            self._render()
            fade_in = QPropertyAnimation(effect, b"opacity", self)
            fade_in.setDuration(60)
            fade_in.setStartValue(0.35)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

            def finish():
                self.charts_host.setGraphicsEffect(None)
                self._mode_animation = None

            fade_in.finished.connect(finish)
            self._mode_animation = fade_in
            fade_in.start()

        fade_out.finished.connect(swap_content)
        self._mode_animation = fade_out
        fade_out.start()

    def set_data(self, daily_tokens, cumulative_total=None, model_usage=None):
        self.daily_tokens = list(daily_tokens or [])
        self.cumulative_total = cumulative_total
        self.model_usage = list(model_usage or [])
        self.data_updated_at = datetime.now(timezone.utc)
        model_keys = {_model_key(model) for model in self.model_usage}
        if self.selected_model_key not in model_keys:
            self.selected_model_key = _model_key(self.model_usage[0]) if self.model_usage else None
            self.selected_model = self.model_usage[0] if self.model_usage else None
        self._render()

    def _period_model(self, model):
        points = aggregate_points(model.daily_tokens, self.mode, model.token_total)
        today = get_statistics_timezone().now_date()
        start = model_period_start(self.mode, today)
        selected_days = [
            item for item in model.daily_tokens
            if _in_period(item.date, start, today)
        ]
        if self.mode == "cumulative":
            tokens = model.tokens
        else:
            tokens = TokenBreakdown(
                cached_input=sum(item.cached_input for item in selected_days),
                uncached_input=sum(item.uncached_input for item in selected_days),
                output=sum(item.output for item in selected_days),
            )
        total = tokens.total
        priced = estimate_model_api_value(tokens, model.name)
        sessions = sum(1 for active in model.session_activity.values() if _in_period(active, start, today))
        turns = sum(1 for active in model.turn_activity.values() if _in_period(active, start, today))
        if not model.session_activity and self.mode == "cumulative":
            sessions = model.session_count
        if not model.turn_activity and self.mode == "cumulative":
            turns = model.turn_count
        return ModelUsage(
            name=model.name,
            effort=model.effort,
            runtime=model.runtime,
            token_total=total,
            estimated_value=priced or 0.0,
            pricing_coverage_pct=100.0 if prices_for_model(model.name) and total else 0.0,
            tokens=tokens,
            session_count=sessions,
            turn_count=turns,
            last_active=model.last_active,
            daily_tokens=model.daily_tokens,
        ), points

    def _activity_model(self, model):
        today = get_statistics_timezone().now_date()
        start = model_activity_start(self.model_activity_window, today)
        selected_days = [
            item for item in model.daily_tokens
            if _in_period(item.date, start, today)
        ]
        tokens = TokenBreakdown(
            cached_input=sum(item.cached_input for item in selected_days),
            uncached_input=sum(item.uncached_input for item in selected_days),
            output=sum(item.output for item in selected_days),
        )
        sessions = sum(1 for active in model.session_activity.values() if _in_period(active, start, today))
        turns = sum(1 for active in model.turn_activity.values() if _in_period(active, start, today))
        return ModelUsage(
            name=model.name,
            effort=model.effort,
            runtime=model.runtime,
            token_total=tokens.total,
            estimated_value=estimate_model_api_value(tokens, model.name) or 0.0,
            pricing_coverage_pct=100.0 if prices_for_model(model.name) and tokens.total else 0.0,
            tokens=tokens,
            session_count=sessions,
            turn_count=turns,
            last_active=model.last_active,
            daily_tokens=selected_days,
            session_activity={
                key: value for key, value in model.session_activity.items()
                if _in_period(value, start, today)
            },
            turn_activity={
                key: value for key, value in model.turn_activity.items()
                if _in_period(value, start, today)
            },
        )

    @staticmethod
    def _merge_models(models, name=OTHER_MODEL_KEY):
        tokens = TokenBreakdown()
        daily = {}
        sessions = {}
        turns = {}
        last_active = None
        priced_tokens = 0.0
        estimated_value = 0.0
        for index, model in enumerate(models):
            tokens.cached_input += model.tokens.cached_input
            tokens.uncached_input += model.tokens.uncached_input
            tokens.output += model.tokens.output
            priced_tokens += model.token_total * model.pricing_coverage_pct / 100.0
            estimated_value += model.estimated_value
            if model.last_active and (last_active is None or model.last_active > last_active):
                last_active = model.last_active
            for item in model.daily_tokens:
                key = _item_date(item)
                target = daily.setdefault(
                    key,
                    DailyToken(date=item.date, runtime=RuntimeScope.CODEX),
                )
                target.cached_input += item.cached_input
                target.uncached_input += item.uncached_input
                target.output += item.output
                target.total = target.cached_input + target.uncached_input + target.output
            for key, value in model.session_activity.items():
                sessions[f"{index}:{key}"] = value
            for key, value in model.turn_activity.items():
                turns[f"{index}:{key}"] = value
        total = tokens.total
        return ModelUsage(
            name=name,
            token_total=total,
            estimated_value=estimated_value,
            pricing_coverage_pct=(priced_tokens / total * 100.0) if total else 0.0,
            tokens=tokens,
            session_count=len(sessions) or sum(model.session_count for model in models),
            turn_count=len(turns) or sum(model.turn_count for model in models),
            last_active=last_active,
            daily_tokens=sorted(daily.values(), key=lambda item: item.date),
            session_activity=sessions,
            turn_activity=turns,
        )

    @staticmethod
    def _sum_points(point_lists):
        point_lists = [points for points in point_lists if points]
        if not point_lists:
            return []
        count = len(point_lists[0])
        return [
            (point_lists[0][index][0], sum(points[index][1] for points in point_lists if index < len(points)))
            for index in range(count)
        ]

    def _select_model(self, model_key):
        self.selected_model_key = model_key
        self._render_models()

    def _clear_model_rows(self):
        while self.models_list_layout.count() > 1:
            item = self.models_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_models_legacy(self):
        self._clear_model_rows()
        english = self.language == "en"
        range_text = model_period_label(self.mode, english)
        period_models = []
        for original in self.model_usage:
            period, points = self._period_model(original)
            if period.token_total:
                period_models.append((original, period, points))
        period_models.sort(key=lambda item: item[1].token_total, reverse=True)
        total = sum(item[1].token_total for item in period_models)
        if not period_models:
            empty = QLabel("No model usage in this period" if english else "当前口径暂无模型用量")
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.models_list_layout.insertWidget(0, empty, 1)
            self.model_detail_title.setText("Model details" if english else "模型详情")
            self.model_detail_meta.setText("")
            self.model_detail_value.setText("0")
            for value_label, name_label in self.model_metric_labels:
                value_label.setText("0")
                name_label.setText("")
            self.model_chart.set_points([])
            return
        originals = [item[0] for item in period_models]
        if self.selected_model not in originals:
            self.selected_model = originals[0]
        selected = period_models[originals.index(self.selected_model)]
        for original, period, _points in period_models:
            row = ModelUsageRow(period, total, english, range_text)
            row.setProperty("selected", original is self.selected_model)
            row.activated.connect(lambda _period, target=original: self._select_model(target))
            self.models_list_layout.insertWidget(self.models_list_layout.count() - 1, row)
        original, period, points = selected
        effort = _effort_label(original.effort, english)
        self.model_detail_title.setText(f"{_model_label(original.name)} · {effort}")
        source = pricing_source_for_model(original.name)
        priced = prices_for_model(original.name) is not None
        value_text = f"${period.estimated_value:,.2f}" if priced else ("Unpriced" if english else "未计价")
        self.model_detail_value.setText(f"{format_tokens(period.token_total)} · {value_text}")
        self.model_detail_value.setToolTip(source or ("No exact official price for this model ID" if english else "未找到与该模型 ID 精确匹配的官方价格"))
        share = period.token_total / max(1, total) * 100
        last_active = get_statistics_timezone().datetime_for(original.last_active).strftime("%m/%d %H:%M") if original.last_active else "--"
        self.model_detail_meta.setText(
            f"{period.session_count} sessions · {period.turn_count} turns · {share:.1f}% share · last active {last_active}"
            if english else f"{period.session_count} 个会话 · {period.turn_count} 个回合 · 占本期 {share:.1f}% · 最近活跃 {last_active}"
        )
        metric_values = (period.tokens.uncached_input, period.tokens.cached_input, period.tokens.output)
        metric_names = ("Uncached", "Cached", "Output") if english else ("未缓存", "缓存", "输出")
        for (value_label, name_label), value, name in zip(self.model_metric_labels, metric_values, metric_names):
            value_label.setText(format_tokens(value))
            name_label.setText(name)
        self.model_chart.set_points(points)

    def _render_models(self):
        self._clear_model_rows()
        english = self.language == "en"
        range_text = model_period_label(self.mode, english)
        period_models = []
        for original in self.model_usage:
            period, _period_points = self._period_model(original)
            if period.token_total:
                activity = self._activity_model(original)
                period_models.append({
                    "key": _model_key(original),
                    "original": original,
                    "period": period,
                    "activity": activity,
                    "points": _daily_metric_points(
                        original, self.model_activity_window, self.model_metric,
                    ),
                })
        period_models.sort(
            key=lambda item: (item["activity"].token_total, item["period"].token_total),
            reverse=True,
        )
        if not period_models:
            empty = QLabel("No model usage in this period" if english else "当前口径暂无模型用量")
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.models_list_layout.insertWidget(0, empty, 1)
            self.model_detail_title.setText("Model details" if english else "模型详情")
            self.model_detail_meta.setText("")
            self.model_detail_value.setText("0")
            for value_label, name_label in self.model_metric_labels:
                value_label.setText("0")
                name_label.setText("")
            self.model_chart.set_points([], metric=self.model_metric, english=english)
            return

        visible = period_models[:8]
        if len(period_models) > 8:
            remainder = period_models[8:]
            visible.append({
                "key": OTHER_MODEL_KEY,
                "original": self._merge_models([item["original"] for item in remainder]),
                "period": self._merge_models([item["period"] for item in remainder]),
                "activity": self._merge_models([item["activity"] for item in remainder]),
                "points": self._sum_points([item["points"] for item in remainder]),
            })

        total = sum(item["period"].token_total for item in visible)
        visible_keys = {item["key"] for item in visible}
        if self.selected_model_key not in visible_keys:
            self.selected_model_key = visible[0]["key"]
        selected = next(item for item in visible if item["key"] == self.selected_model_key)
        self.selected_model = selected["original"]

        for item in visible:
            row = ModelUsageRow(
                item["period"], total, english, range_text, self.model_metric,
            )
            row.setProperty("selected", item["key"] == self.selected_model_key)
            row.activated.connect(lambda _model, target=item["key"]: self._select_model(target))
            self.models_list_layout.insertWidget(self.models_list_layout.count() - 1, row)

        period = selected["period"]
        effort = _effort_label(period.effort, english) if period.effort else ""
        title = _model_label(period.name, english)
        self.model_detail_title.setText(f"{title} · {effort}" if effort else title)
        api_text = _api_value_text(period, english)
        token_text = format_tokens(period.token_total)
        if self.model_metric == "api":
            value_text = f"{api_text} · {token_text} Token"
        else:
            value_text = f"{token_text} · API {api_text}"
        self.model_detail_value.setText(value_text)
        source = pricing_source_for_model(period.name)
        self.model_detail_value.setToolTip(
            source or ("No exact official price for this model ID" if english else "未找到与该模型 ID 精确匹配的官方价格")
        )
        share = period.token_total / max(1, total) * 100
        last_active = (
            get_statistics_timezone().datetime_for(period.last_active).strftime("%m/%d %H:%M")
            if period.last_active else "--"
        )
        baseline_points = self._sum_points([item["points"] for item in period_models])
        baseline_total = baseline_points[-1][1] if baseline_points else 0
        activity_range = model_activity_range_text(self.model_activity_window, english)
        baseline_text = format_metric_value(baseline_total, self.model_metric, english)
        self.model_detail_meta.setText(
            f"{period.session_count} sessions · {period.turn_count} turns · {share:.1f}% share · "
            f"activity {activity_range} · total {baseline_text} · last active {last_active}"
            if english else
            f"{period.session_count} 个会话 · {period.turn_count} 个回合 · 占比 {share:.1f}% · "
            f"活动范围 {activity_range} · 总量基线 {baseline_text} · 最近活跃 {last_active}"
        )
        metric_values = (period.tokens.uncached_input, period.tokens.cached_input, period.tokens.output)
        metric_names = (
            ("Uncached", "Cached", "Output") if english else ("未缓存", "缓存", "输出")
        )
        for (value_label, name_label), value, name in zip(self.model_metric_labels, metric_values, metric_names):
            value_label.setText(format_tokens(value))
            name_label.setText(name)

        series = []
        for item in visible:
            model = item["activity"]
            model_name = _model_label(model.name, english)
            model_effort = _effort_label(model.effort, english) if model.effort else ""
            label = f"{model_name} · {model_effort}" if model_effort else model_name
            series.append((label, item["points"]))
        self.model_chart.set_series(
            series,
            baseline=baseline_points,
            metric=self.model_metric,
            english=english,
        )

    def _render(self):
        english = self.language == "en"
        self._update_period_controls()
        self.stats.set_data(self.daily_tokens, english, self.cumulative_total)
        points = aggregate_points(self.daily_tokens, self.mode, self.cumulative_total)
        self.chart.set_points(points)
        if self.mode == "daily":
            self.activity_stack.setCurrentIndex(0)
            self.heatmap.set_data(self.daily_tokens)
        else:
            self.activity_stack.setCurrentIndex(1)
            self.bars.set_points(points)
        mode_names = {mode: period_label(mode, english) for mode in MODES}
        self.trend_title.setText(("Trend · " if english else "趋势 · ") + mode_names[self.mode])
        self._render_models()
