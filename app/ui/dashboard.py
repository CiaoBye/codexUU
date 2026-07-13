from __future__ import annotations

import math
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
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

from app.data.claude_reader import (
    read_claude_daily_tokens,
    read_claude_projects,
    read_claude_skill_usage,
    read_claude_snapshot,
    read_claude_tasks,
    read_claude_tool_usage,
)
from app.data.codex_reader import (
    read_codex_snapshot,
    read_daily_tokens,
    read_projects,
    read_skill_usage,
    read_task_board,
    read_tool_usage,
)
from app.data.models import (
    FULL_MONTHLY_VALUE,
    MultiRuntimeUsageSnapshot,
    RuntimeScope,
    format_tokens,
)
from app.ui.project_ranking import ProjectRankingWidget
from app.ui.skill_usage import SkillUsageWidget
from app.ui.task_board import TaskBoardWidget
from app.ui.usage_chart import UsageTrendWidget
from app.utils.statistics_timezone import get_statistics_timezone


ICONS_DIR = Path(__file__).resolve().parents[2] / "resources" / "icons"


def icon_path(name: str) -> str:
    return str(ICONS_DIR / name)


class Surface(QFrame):
    def __init__(self, object_name: str = "surfaceCard", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


class MetricCard(Surface):
    def __init__(self, label: str, icon: str, parent=None):
        super().__init__(parent=parent)
        self.setMinimumHeight(128)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(13, 24, 45, 34))
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(6)

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
        self.trend_badge = QLabel("")
        self.trend_badge.setObjectName("neutralBadge")
        self.trend_badge.hide()
        value_row.addWidget(self.trend_badge)
        layout.addLayout(value_row)
        layout.addStretch()
        self.breakdown = QLabel("未缓存 0  ·  缓存 0  ·  输出 0")
        self.breakdown.setObjectName("metricHint")
        self.breakdown.setTextFormat(Qt.TextFormat.RichText)
        self.breakdown.setMinimumHeight(30)
        self.breakdown.setWordWrap(True)
        layout.addWidget(self.breakdown)
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

    def set_badge(self, text="", tone="neutral"):
        self.trend_badge.setText(text)
        self.trend_badge.setObjectName(f"{tone}Badge")
        self.trend_badge.style().unpolish(self.trend_badge)
        self.trend_badge.style().polish(self.trend_badge)
        self.trend_badge.setVisible(bool(text))

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
        if self.language == "en":
            self.breakdown.setText(
                f'<span style="color:#3f95ff">Uncached {values[0]}</span> · '
                f'<span style="color:#8d74ff">Cached {values[1]}</span><br>'
                f'<span style="color:#e99a25">Output {values[2]}</span>'
            )
        else:
            self.breakdown.setText(
                f'<span style="color:#3f95ff">未缓存 {values[0]}</span> · '
                f'<span style="color:#8d74ff">缓存 {values[1]}</span><br>'
                f'<span style="color:#e99a25">输出 {values[2]}</span>'
            )


class QuotaDial(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.q5 = None
        self.q7 = None
        self.language = "zh"
        self.display_mode = "remaining"
        self.setMinimumSize(168, 164)

    def set_quota(self, q5, q7):
        self.q5, self.q7 = q5, q7
        self.update()

    def set_language(self, language):
        self.language = language
        self.update()

    def set_display_mode(self, mode):
        self.display_mode = mode if mode in ("remaining", "used") else "remaining"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 22
        bounds = QRectF((self.width() - side) / 2, 7, side, side)
        available = [
            item for item in (
                ("5h", self.q5, QColor("#3992ff")),
                ("7d", self.q7, QColor("#8d74ff")),
            ) if item[1] is not None
        ]
        for index, (_, quota, color) in enumerate(available):
            inset = index * 20 if len(available) > 1 else 8
            rect = bounds.adjusted(inset, inset, -inset, -inset)
            painter.setPen(QPen(QColor(127, 145, 172, 38), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 0, 360 * 16)
            value = quota.used_pct if self.display_mode == "used" else quota.remaining_pct
            value = max(0.0, min(100.0, value))
            painter.setPen(QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            direction = 1 if self.display_mode == "used" else -1
            painter.drawArc(rect, 90 * 16, int(direction * 360 * 16 * value / 100))

        painter.setPen(QColor("#172033") if self.palette().window().color().lightness() > 128 else QColor("#f8fafc"))
        painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        center = bounds.center()
        if not available:
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Medium))
            text = "Unavailable" if self.language == "en" else "暂不可用"
            painter.drawText(QRectF(center.x() - 54, center.y() - 12, 108, 24), Qt.AlignmentFlag.AlignCenter, text)
            return
        line_height = 24
        start_y = center.y() - line_height * len(available) / 2
        for index, (label, quota, _) in enumerate(available):
            value = quota.used_pct if self.display_mode == "used" else quota.remaining_pct
            text = f"{label}  {value:.0f}%"
            painter.drawText(
                QRectF(center.x() - 48, start_y + index * line_height, 96, line_height),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )


class QuotaResetRow(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
        layout.addWidget(dot)
        self.label = QLabel()
        self.label.setObjectName("caption")
        layout.addWidget(self.label)
        layout.addStretch()
        self.time = QLabel()
        self.time.setObjectName("metricLabel")
        self.time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.time)

    def update_value(self, prefix, quota, english=False):
        self.setVisible(quota is not None)
        if quota is None:
            return
        self.label.setText(f"{prefix} reset" if english else f"{prefix} 重置")
        if quota.reset_time is None:
            self.time.setText("--")
            self.setToolTip("")
            return
        local_time = quota.reset_time.astimezone(get_statistics_timezone().tzinfo())
        self.time.setText(local_time.strftime("%H:%M") if prefix == "5h" else local_time.strftime("%m/%d %H:%M"))
        self.setToolTip(local_time.strftime("%Y-%m-%d %H:%M:%S %Z"))


class QuotaPanel(Surface):
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedWidth(216)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        header = QHBoxLayout()
        header.setSpacing(4)
        self.title = QLabel("额度窗口")
        self.title.setObjectName("sectionTitle")
        header.addWidget(self.title)
        header.addStretch()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = {}
        for mode, text in (("remaining", "剩余"), ("used", "已用")):
            button = QPushButton(text)
            button.setObjectName("quotaToggle")
            button.setCheckable(True)
            button.setChecked(mode == "remaining")
            button.setFixedHeight(24)
            button.clicked.connect(lambda checked=False, value=mode: self._select_mode(value))
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            header.addWidget(button)
        layout.addLayout(header)
        self.dial = QuotaDial()
        layout.addWidget(self.dial, 1)
        self.reset_5h = QuotaResetRow("#3992ff")
        self.reset_7d = QuotaResetRow("#8d74ff")
        layout.addWidget(self.reset_5h)
        layout.addWidget(self.reset_7d)
        self.language = "zh"
        self.q5 = None
        self.q7 = None
        self.display_mode = "remaining"

    def _select_mode(self, mode):
        self.set_display_mode(mode)
        self.mode_changed.emit(mode)

    def set_display_mode(self, mode):
        self.display_mode = mode if mode in ("remaining", "used") else "remaining"
        self.mode_buttons[self.display_mode].setChecked(True)
        self.dial.set_display_mode(self.display_mode)

    def update_quota(self, q5, q7):
        self.q5, self.q7 = q5, q7
        self.dial.set_quota(q5, q7)
        english = self.language == "en"
        self.reset_5h.update_value("5h", q5, english)
        self.reset_7d.update_value("7d", q7, english)

    def set_language(self, language):
        self.language = language
        self.dial.set_language(language)
        self.mode_buttons["remaining"].setText("Remaining" if language == "en" else "剩余")
        self.mode_buttons["used"].setText("Used" if language == "en" else "已用")
        self.update_quota(self.q5, self.q7)


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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, y = 6, 6, 8
        width = max(1, self.width() - left - right)
        painter.setPen(QPen(QColor(127, 145, 172, 42), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(left, y, left + width, y)
        progress_x = left + width * self.position(self.value)
        painter.setPen(QPen(QColor("#4e82e3"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(left, y, int(progress_x), y)
        painter.setFont(QFont("Microsoft YaHei", 8))
        for label, amount in self.MILESTONES:
            x = left + width * self.position(amount)
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#6d9dff"), 2))
            painter.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
            painter.setPen(QColor("#748197"))
            painter.drawText(QRectF(x - 34, 17, 68, 15), Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QColor("#748197"))
        painter.drawText(QRectF(self.width() - 72, 17, 68, 15), Qt.AlignmentFlag.AlignRight, "$46.5K")


class ValueCard(Surface):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setMinimumHeight(94)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 11, 15, 11)
        layout.setSpacing(7)
        header = QHBoxLayout()
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

    def update_value(self, value: float, coverage: float = 100.0, unpriced_tokens: int = 0):
        self.coverage = coverage
        self.unpriced_tokens = unpriced_tokens
        self.value.setText(f"${value:,.2f} / $46.5K")
        self.bar.set_value(value)
        self._update_hint()

    def set_language(self, language):
        self.language = language
        self._update_hint()

    def set_reduce_motion(self, enabled):
        self.bar.reduce_motion = bool(enabled)

    def _update_hint(self):
        if self.unpriced_tokens:
            self.hint.setText(
                f"Official price coverage {self.coverage:.0f}% · other models unpriced"
                if self.language == "en"
                else f"官方价格计价覆盖 {self.coverage:.0f}% · 其余模型未计价"
            )
        else:
            self.hint.setText("Estimated with official model prices" if self.language == "en" else "按官方模型价格估算")


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
    request_close = Signal()
    data_updated = Signal(object)

    def __init__(self, parent=None, settings_manager=None, translation_manager=None, theme_manager=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        runtime = settings_manager.get_active_runtime() if settings_manager else "codex"
        self.current_scope = RuntimeScope.CLAUDE_CODE if runtime == "claudeCode" else RuntimeScope.CODEX
        self.data = MultiRuntimeUsageSnapshot()
        self._pending_result = None
        self._loading = False
        self._pending_error = None

        self.setObjectName("dashboard")
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(12)
        root.addLayout(self._build_header())
        root.addWidget(self._build_summary())
        root.addWidget(self._build_tab_area(), 1)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._check_worker)
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

        self.refresh_feedback = QLabel()
        self.refresh_feedback.setObjectName("statusPill")
        self.refresh_feedback.hide()
        header.addWidget(self.refresh_feedback)

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
        self.close_button = QPushButton()
        self.close_button.setIcon(QIcon(icon_path("close.svg")))
        self.close_button.setIconSize(QSize(16, 16))
        self.close_button.setObjectName("iconButton")
        self.close_button.setToolTip("隐藏窗口")
        self.close_button.setFixedSize(34, 34)
        self.close_button.clicked.connect(self.request_close.emit)
        header.addWidget(self.close_button)
        return header

    def _build_summary(self):
        summary = QFrame()
        summary.setObjectName("summaryPanel")
        summary.setFixedHeight(260)
        layout = QHBoxLayout(summary)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
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
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.tab_bar = SlidingTabBar(("今日任务", "用量趋势", "项目排行", "Skill"))
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
        self.trend_tab = UsageTrendWidget()
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

    def _on_settings_changed(self):
        if not self.settings_manager:
            return
        runtime = self.settings_manager.get_active_runtime()
        scope = RuntimeScope.CLAUDE_CODE if runtime == "claudeCode" else RuntimeScope.CODEX
        if scope != self.current_scope:
            self.current_scope = scope
            self._update()
        theme = self.settings_manager.get_theme()
        if theme in self.theme_buttons:
            self.theme_buttons[theme].setChecked(True)
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
        self.language_buttons["en" if english else "zh"].setChecked(True)
        self.quota_card.title.setText("Quota windows" if english else "额度窗口")
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

    def refresh(self):
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self):
        if self._loading:
            return
        self._loading = True
        self.refresh_button.setEnabled(False)
        self.refresh_button.setIcon(QIcon())
        self.refresh_button.setText("…")
        self.refresh_button.setToolTip("Refreshing…" if self._is_english() else "正在刷新…")
        self._show_refresh_feedback("Refreshing…" if self._is_english() else "正在刷新…")
        self._pending_result = None
        self._pending_error = None

        def load():
            try:
                codex = read_codex_snapshot()
                claude = read_claude_snapshot()
                tasks = read_task_board() + read_claude_tasks()
                daily = read_daily_tokens() + read_claude_daily_tokens()
                daily.sort(key=lambda item: item.date, reverse=True)
                projects = read_projects() + read_claude_projects()
                projects.sort(key=lambda item: item.token_total, reverse=True)
                tools = read_tool_usage() + read_claude_tool_usage()
                skills = read_skill_usage() + read_claude_skill_usage()
                self._pending_result = (codex, claude, tasks, daily, projects, tools, skills)
            except Exception as error:
                self._pending_error = str(error)
                traceback.print_exc()
            finally:
                self._loading = False

        self._poll_timer.start()
        threading.Thread(target=load, daemon=True).start()

    def _check_worker(self):
        if self._pending_result is not None:
            self._poll_timer.stop()
            result = self._pending_result
            self._pending_result = None
            codex, claude, tasks, daily, projects, tools, skills = result
            self.data.codex = codex
            self.data.claude_code = claude
            self.data.tasks = tasks
            self.data.daily_tokens = daily
            self.data.projects = projects
            self.data.tools = tools
            self.data.skills = skills
            self.refresh_button.setEnabled(True)
            self._restore_refresh_button()
            self._update()
            now = datetime.now().strftime("%H:%M:%S")
            self.refresh_button.setToolTip(
                f"Updated at {now}" if self._is_english() else f"刷新完成 · {now}"
            )
            self._show_refresh_feedback(
                f"Updated {now}" if self._is_english() else f"已刷新 {now}", 2600,
            )
        elif not self._loading:
            self._poll_timer.stop()
            self.refresh_button.setEnabled(True)
            self._restore_refresh_button()
            if self._pending_error:
                self.refresh_button.setToolTip(
                    f"Refresh failed: {self._pending_error}" if self._is_english()
                    else f"刷新失败：{self._pending_error}"
                )
                self._show_refresh_feedback("Refresh failed" if self._is_english() else "刷新失败", 3600)

    def _restore_refresh_button(self):
        self.refresh_button.setText("")
        self.refresh_button.setIcon(QIcon(icon_path("refresh.svg")))
        self.refresh_button.setIconSize(QSize(16, 16))

    def _is_english(self):
        return bool(self.translation_manager and self.translation_manager.get_language() == "en")

    def _show_refresh_feedback(self, text, timeout=0):
        self.refresh_feedback.setText(text)
        self.refresh_feedback.show()
        if timeout:
            QTimer.singleShot(timeout, self.refresh_feedback.hide)

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
            f"{len(tasks)} items" if english else f"{len(tasks)} 事项",
            f"{len(daily)} active days" if english else f"{len(daily)} 活跃日",
            f"{len(projects)} projects" if english else f"{len(projects)} 项目",
            f"{len(skills)} skills · {len(tools)} calls" if english else f"{len(skills)} Skill · {len(tools)} 次调用",
        )
        self.tab_summary.setText(summaries[index])

    def _update(self):
        snapshot = self.data.for_scope(self.current_scope)
        self.quota_card.update_quota(snapshot.quota_5h, snapshot.quota_7d)
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

        tasks, daily, projects, tools, skills = self._visible_data()
        self._update_metric_badges(daily, snapshot)
        self.task_tab.update_tasks(tasks)
        self.trend_tab.set_data(daily, snapshot.cumulative_index_total or snapshot.tokens.cumulative.total)
        self.project_tab.update_projects(projects)
        self.skill_tab.set_data(skills, tools)
        self._update_tab_summary()
        self.data_updated.emit(self.data)

    def _update_metric_badges(self, daily, snapshot):
        totals = {}
        for item in daily:
            day = item.date.date() if hasattr(item.date, "date") else item.date
            totals[day] = totals.get(day, 0) + item.total
        today = get_statistics_timezone().now_date()
        week_start = today - timedelta(days=today.weekday())
        previous_week = sum(
            value for day, value in totals.items()
            if week_start - timedelta(days=7) <= day < week_start
        )
        month_start = today.replace(day=1)
        previous_month_end = month_start - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        previous_month = sum(
            value for day, value in totals.items()
            if previous_month_start <= day <= previous_month_end
        )

        def badge(card, current, previous):
            if previous <= 0:
                text = "New" if self._is_english() else "新增"
                card.set_badge(text, "positive" if current > 0 else "neutral")
                return
            change = (current - previous) / previous * 100
            card.set_badge(f"{change:+.0f}%", "positive" if change >= 0 else "negative")

        badge(self.today_card, snapshot.tokens.today.total, totals.get(today - timedelta(days=1), 0))
        badge(self.week_card, snapshot.tokens.current_week.total, previous_week)
        badge(self.month_card, snapshot.tokens.current_month.total, previous_month)
        coverage = f"Priced {snapshot.pricing_coverage_pct:.0f}%" if self._is_english() else f"计价 {snapshot.pricing_coverage_pct:.0f}%"
        self.cumulative_card.set_badge(coverage, "neutral")
