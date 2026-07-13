from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.data.models import ProjectStats, format_tokens
from app.utils.statistics_timezone import get_statistics_timezone


MODES = ("week", "month", "all")


def project_values(project: ProjectStats, mode: str):
    if mode == "week":
        return (
            project.current_week_token_total or 0,
            project.current_week_estimated_value or 0.0,
            project.current_week_pricing_coverage_pct,
        )
    if mode == "month":
        return (
            project.current_month_token_total or 0,
            project.current_month_estimated_value or 0.0,
            project.current_month_pricing_coverage_pct,
        )
    return project.token_total, project.estimated_value, project.pricing_coverage_pct


def _value_text(value: float, coverage: float, english=False):
    if coverage <= 0:
        return "Unpriced" if english else "未计价"
    return f"{'~' if coverage < 99.5 else ''}${value:.2f}"


class ProjectUsageRow(QFrame):
    def __init__(self, project, rank, mode, maximum, english=False, parent=None):
        super().__init__(parent)
        self.setObjectName("projectUsageRow")
        self.setFixedHeight(66)
        token_total, estimated_value, coverage = project_values(project, mode)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)
        rank_label = QLabel(f"{rank:02d}")
        rank_label.setObjectName("projectRank")
        rank_label.setFixedWidth(24)
        top.addWidget(rank_label)
        name_box = QVBoxLayout()
        name_box.setSpacing(1)
        name = QLabel(project.name or "default")
        name.setObjectName("projectName")
        name.setToolTip(project.name)
        name_box.addWidget(name)
        active = project.last_active.strftime("%m/%d %H:%M") if project.last_active else "--"
        detail = (
            f"{project.thread_count} threads · active {active}"
            if english else f"{project.thread_count} 线程 · 活跃于 {active}"
        )
        detail_label = QLabel(detail)
        detail_label.setObjectName("caption")
        name_box.addWidget(detail_label)
        top.addLayout(name_box, 1)
        value_box = QVBoxLayout()
        value_box.setSpacing(1)
        token_label = QLabel(format_tokens(token_total))
        token_label.setObjectName("projectToken")
        token_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        value_box.addWidget(token_label)
        price = QLabel(_value_text(estimated_value, coverage, english))
        price.setObjectName("caption")
        price.setAlignment(Qt.AlignmentFlag.AlignRight)
        value_box.addWidget(price)
        top.addLayout(value_box)
        layout.addLayout(top)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(32, 0, 0, 0)
        bar = QProgressBar()
        bar.setObjectName("projectBar")
        bar.setRange(0, 1000)
        bar.setValue(round(token_total / max(1, maximum) * 1000))
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        progress_row.addWidget(bar)
        layout.addLayout(progress_row)


class OverviewMetric(QFrame):
    def __init__(self, label, value, accent, parent=None):
        super().__init__(parent)
        self.setObjectName("overviewMetric")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(2)
        title = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(f"background: {accent}; border-radius: 3px;")
        title.addWidget(dot)
        caption = QLabel(label)
        caption.setObjectName("caption")
        title.addWidget(caption)
        title.addStretch()
        layout.addLayout(title)
        number = QLabel(value)
        number.setObjectName("overviewValue")
        layout.addWidget(number)


class RecentProjectRow(QFrame):
    def __init__(self, project, mode, english=False, parent=None):
        super().__init__(parent)
        self.setObjectName("recentProjectRow")
        self.setFixedHeight(47)
        token_total, _, _ = project_values(project, mode)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(8)
        marker = QLabel()
        marker.setObjectName("projectMarker")
        marker.setFixedSize(22, 22)
        layout.addWidget(marker)
        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(project.name or "default")
        name.setObjectName("projectName")
        text.addWidget(name)
        active = project.last_active.strftime("%m/%d %H:%M") if project.last_active else "--"
        detail = f"{project.thread_count} threads · {active}" if english else f"{project.thread_count} 线程 · {active}"
        subtitle = QLabel(detail)
        subtitle.setObjectName("caption")
        text.addWidget(subtitle)
        layout.addLayout(text, 1)
        token = QLabel(format_tokens(token_total))
        token.setObjectName("metricLabel")
        layout.addWidget(token)


class ProjectRankingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects = []
        self.mode = "week"
        self.language = "zh"
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.ranking_card = QFrame()
        self.ranking_card.setObjectName("surfaceCard")
        left = QVBoxLayout(self.ranking_card)
        left.setContentsMargins(13, 10, 13, 10)
        left.setSpacing(8)
        header = QHBoxLayout()
        self.ranking_title = QLabel("项目用量排行")
        self.ranking_title.setObjectName("sectionTitle")
        header.addWidget(self.ranking_title)
        header.addStretch()
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
            header.addWidget(button)
        left.addLayout(header)
        self.ranking_scroll, self.ranking_container, self.ranking_layout = self._scroll_column()
        left.addWidget(self.ranking_scroll, 1)
        root.addWidget(self.ranking_card, 11)

        self.overview_card = QFrame()
        self.overview_card.setObjectName("surfaceCard")
        right = QVBoxLayout(self.overview_card)
        right.setContentsMargins(13, 10, 13, 10)
        right.setSpacing(8)
        overview_header = QHBoxLayout()
        self.overview_title = QLabel("项目活动概览")
        self.overview_title.setObjectName("sectionTitle")
        overview_header.addWidget(self.overview_title)
        overview_header.addStretch()
        self.overview_badge = QLabel("0")
        self.overview_badge.setObjectName("countBadge")
        overview_header.addWidget(self.overview_badge)
        right.addLayout(overview_header)
        self.metrics = QGridLayout()
        self.metrics.setSpacing(7)
        right.addLayout(self.metrics)
        self.recent_title = QLabel("最近活跃")
        self.recent_title.setObjectName("metricLabel")
        right.addWidget(self.recent_title)
        self.recent_scroll, self.recent_container, self.recent_layout = self._scroll_column()
        right.addWidget(self.recent_scroll, 1)
        root.addWidget(self.overview_card, 9)
        self.set_language("zh")

    @staticmethod
    def _scroll_column():
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(6)
        scroll.setWidget(container)
        return scroll, container, layout

    def set_language(self, language):
        self.language = language
        english = language == "en"
        labels = ("This week", "This month", "All time") if english else ("本周", "本月", "累计")
        for mode, label in zip(MODES, labels):
            self.mode_buttons[mode].setText(label)
        self.ranking_title.setText("Project usage ranking" if english else "项目用量排行")
        self.overview_title.setText("Project activity overview" if english else "项目活动概览")
        self.recent_title.setText("Recently active" if english else "最近活跃")
        self._render()

    def set_mode(self, mode):
        if mode not in MODES or mode == self.mode:
            return
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        self._render()

    def update_projects(self, projects):
        self._projects = list(projects or [])
        self._render()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _new_count(self, projects):
        if self.mode == "all":
            return len(projects)
        today = get_statistics_timezone().now_date()
        start = today - timedelta(days=today.weekday()) if self.mode == "week" else today.replace(day=1)
        return sum(
            1 for project in projects
            if project.last_active and get_statistics_timezone().date_for(project.last_active) >= start
        )

    def _render(self):
        self._clear(self.ranking_layout)
        self._clear(self.recent_layout)
        self._clear(self.metrics)
        english = self.language == "en"
        ordered = sorted(self._projects, key=lambda item: project_values(item, self.mode)[0], reverse=True)
        active = [project for project in ordered if project_values(project, self.mode)[0] > 0]
        total = sum(project_values(project, self.mode)[0] for project in active)
        maximum = project_values(active[0], self.mode)[0] if active else 1
        if not active:
            empty = QLabel("No usage in this period" if english else "本期暂无项目用量")
            empty.setObjectName("caption")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ranking_layout.addWidget(empty)
        for rank, project in enumerate(active[:20], 1):
            self.ranking_layout.addWidget(ProjectUsageRow(project, rank, self.mode, maximum, english))

        top1 = project_values(active[0], self.mode)[0] / total * 100 if total and active else 0
        top3 = sum(project_values(item, self.mode)[0] for item in active[:3]) / total * 100 if total else 0
        new_count = self._new_count(active)
        metric_data = (
            (("Active projects", str(len(active)), "#5e91f4"), ("New this period", str(new_count), "#41c878"),
             ("Top 1 share", f"{top1:.0f}%", "#8d74ff"), ("Top 3 share", f"{top3:.0f}%", "#f6a723"))
            if english else
            (("活跃项目", str(len(active)), "#5e91f4"), ("本期新增", str(new_count), "#41c878"),
             ("Top1 占比", f"{top1:.0f}%", "#8d74ff"), ("Top3 占比", f"{top3:.0f}%", "#f6a723"))
        )
        for index, data in enumerate(metric_data):
            self.metrics.addWidget(OverviewMetric(*data), index // 2, index % 2)
        self.overview_badge.setText(
            f"{len(active)} active" if english else f"{len(active)} 活跃"
        )

        recent = sorted(
            self._projects,
            key=lambda item: item.last_active.timestamp() if item.last_active else 0,
            reverse=True,
        )
        for project in recent[:8]:
            self.recent_layout.addWidget(RecentProjectRow(project, self.mode, english))
        if not recent:
            empty = QLabel("No recent projects" if english else "暂无最近项目")
            empty.setObjectName("caption")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.recent_layout.addWidget(empty)
