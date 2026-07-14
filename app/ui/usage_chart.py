from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QPointF, QRectF, Signal
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
    TokenBreakdown,
    estimate_model_api_value,
    format_tokens,
    pricing_source_for_model,
    prices_for_model,
)
from app.ui.heatmap import TokenHeatmap
from app.utils.statistics_timezone import get_statistics_timezone


MODES = ("daily", "weekly", "monthly", "cumulative")
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


def _in_period(value: datetime | None, start: date | None, end: date) -> bool:
    if value is None:
        return False
    day = value.date() if hasattr(value, "date") else value
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
        return [(f"{start.month}月", buckets[start]) for start in starts]

    starts = sorted(buckets)
    known_total = sum(buckets.values())
    running = max(0, int(cumulative_total or 0) - known_total)
    result = []
    for start in starts:
        running += buckets[start]
        result.append((f"{start.month}月", running))
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


def _model_label(name: str) -> str:
    value = (name or "unknown").strip()
    aliases = {
        "gpt-5.6-sol": "Sol",
        "gpt-5.6-terra": "Terra",
        "gpt-5.6-luna": "Luna",
    }
    return aliases.get(value.lower(), value)


def _effort_label(effort: str, english: bool) -> str:
    key = (effort or "").strip().lower()
    zh = {"low": "低", "medium": "中", "high": "高", "xhigh": "超高", "max": "极高", "ultra": "极限"}
    en = {"low": "Low", "medium": "Medium", "high": "High", "xhigh": "X-high", "max": "Max", "ultra": "Ultra"}
    return (en if english else zh).get(key, "Not provided" if english else "未提供")


class ModelUsageRow(QFrame):
    activated = Signal(object)

    def __init__(self, model: ModelUsage, total: int, english: bool, period_text: str, parent=None):
        super().__init__(parent)
        self.model = model
        self.setObjectName("modelUsageRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 7, 11, 7)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        name = QLabel(f"{_model_label(model.name)} · {_effort_label(model.effort, english)}")
        name.setObjectName("modelUsageName")
        heading.addWidget(name)
        heading.addStretch()
        value = QLabel(format_tokens(model.token_total))
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
    def __init__(self, bars=False, parent=None):
        super().__init__(parent)
        self.bars = bars
        self.points = []
        self.hover_index = -1
        self.setMinimumHeight(210)
        self.setMouseTracking(True)

    def set_points(self, points):
        self.points = list(points or [])
        self.hover_index = -1
        self.update()

    def mouseMoveEvent(self, event):
        if not self.points:
            return
        left, right = 44, 16
        width = max(1, self.width() - left - right)
        index = round((event.position().x() - left) / width * max(1, len(self.points) - 1))
        self.hover_index = max(0, min(len(self.points) - 1, index))
        label, value = self.points[self.hover_index]
        QToolTip.showText(event.globalPosition().toPoint(), f"{label}\n{format_tokens(value)} token", self)
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
        left, top, right, bottom = 44, 14, 16, 28
        width = max(1, self.width() - left - right)
        height = max(1, self.height() - top - bottom)
        maximum = max(value for _, value in self.points) or 1
        painter.setFont(QFont("Microsoft YaHei", 8))
        for pct in (0, 0.5, 1):
            y = top + height * (1 - pct)
            painter.setPen(QPen(QColor(127, 145, 172, 36), 1))
            painter.drawLine(left, int(y), self.width() - right, int(y))
            painter.setPen(QColor("#8a94a6"))
            painter.drawText(QRectF(0, y - 7, 38, 14), Qt.AlignmentFlag.AlignRight, format_tokens(int(maximum * pct)))

        count = len(self.points)
        coords = []
        for index, (_, value) in enumerate(self.points):
            x = left + width * (index + (0.5 if self.bars else 0)) / (count if self.bars else max(1, count - 1))
            y = top + height * (1 - value / maximum)
            coords.append(QPointF(x, y))
        if self.bars:
            bar_width = max(5, min(22, width / max(1, count) * 0.55))
            for index, point in enumerate(coords):
                color = QColor("#6d9dff") if index != self.hover_index else QColor("#326ad6")
                painter.fillRect(QRectF(point.x() - bar_width / 2, point.y(), bar_width, top + height - point.y()), color)
        else:
            area = QPainterPath(coords[0])
            for point in coords[1:]:
                area.lineTo(point)
            area.lineTo(coords[-1].x(), top + height)
            area.lineTo(coords[0].x(), top + height)
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
        step = max(1, count // 6)
        for index, (label, _) in enumerate(self.points):
            if index not in (0, count - 1) and index % step:
                continue
            x = coords[index].x()
            painter.drawText(QRectF(x - 30, self.height() - 20, 60, 15), Qt.AlignmentFlag.AlignCenter, label)


class UsageTrendWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.daily_tokens = []
        self.model_usage = []
        self.selected_model = None
        self.cumulative_total = None
        self.mode = "daily"
        self.language = "zh"
        self._mode_animation = None
        self.reduce_motion = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
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

        self.charts_host = QWidget()
        charts = QHBoxLayout(self.charts_host)
        charts.setContentsMargins(0, 0, 0, 0)
        charts.setSpacing(10)
        left = QFrame()
        left.setObjectName("surfaceCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 10, 14, 10)
        left_header = QHBoxLayout()
        left_header.addWidget(_header_icon("activity.svg"))
        self.activity_title = QLabel("Token 活动")
        self.activity_title.setObjectName("sectionTitle")
        left_header.addWidget(self.activity_title)
        left_header.addStretch()
        self.summary = QLabel("")
        self.summary.setObjectName("metricHint")
        left_header.addWidget(self.summary)
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
        right_layout.setContentsMargins(14, 10, 14, 10)
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
        ranking_layout.setContentsMargins(14, 10, 14, 10)
        self.models_title = QLabel("")
        self.models_title.setObjectName("sectionTitle")
        ranking_layout.addWidget(self.models_title)
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
        detail_layout.setContentsMargins(14, 10, 14, 10)
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
            tile_layout.setContentsMargins(9, 7, 9, 7)
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
        labels = ("Daily", "Weekly", "Monthly", "Cumulative") if english else ("每日", "每周", "每月", "累计")
        for mode, label in zip(MODES, labels):
            self.mode_buttons[mode].setText(label)
        self.activity_title.setText("Token activity" if english else "Token 活动")
        self.overview_button.setText("Overview" if english else "概览")
        self.models_button.setText("Models" if english else "模型")
        self.models_title.setText("Model usage" if english else "模型使用量")
        self._render()

    def _set_view(self, index):
        self.content_stack.setCurrentIndex(index)

    def set_reduce_motion(self, enabled):
        self.reduce_motion = bool(enabled)

    def set_mode(self, mode):
        if mode not in MODES or mode == self.mode:
            return
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
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
        if self.selected_model not in self.model_usage:
            self.selected_model = self.model_usage[0] if self.model_usage else None
        self._render()

    def _period_model(self, model):
        points = aggregate_points(model.daily_tokens, self.mode, model.token_total)
        today = get_statistics_timezone().now_date()
        start = period_start(self.mode, today)
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

    def _select_model(self, model):
        self.selected_model = model
        self._render_models()

    def _clear_model_rows(self):
        while self.models_list_layout.count() > 1:
            item = self.models_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_models(self):
        self._clear_model_rows()
        english = self.language == "en"
        range_text = period_label(self.mode, english)
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
        last_active = original.last_active.strftime("%m/%d %H:%M") if original.last_active else "--"
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

    def _render(self):
        english = self.language == "en"
        self.stats.set_data(self.daily_tokens, english, self.cumulative_total)
        points = aggregate_points(self.daily_tokens, self.mode, self.cumulative_total)
        self.chart.set_points(points)
        if self.mode == "daily":
            self.activity_stack.setCurrentIndex(0)
            self.heatmap.set_data(self.daily_tokens)
        else:
            self.activity_stack.setCurrentIndex(1)
            self.bars.set_points(points)
        total = points[-1][1] if self.mode == "cumulative" and points else sum(value for _, value in points)
        mode_names = {mode: period_label(mode, english) for mode in MODES}
        self.summary.setText(f"{mode_names[self.mode]} · {format_tokens(total)}")
        self.trend_title.setText(("Trend · " if english else "趋势 · ") + mode_names[self.mode])
        self._render_models()
