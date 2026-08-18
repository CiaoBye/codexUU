from __future__ import annotations
import re
import webbrowser

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPixmap, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QGridLayout, QApplication,
)

from app.data.models import TaskItem, RuntimeScope
from app.utils.statistics_timezone import get_statistics_timezone

FONT = "Microsoft YaHei"

STATUS_COLORS = {
    "running": "#22c55e",
    "pending": "#f59e0b",
    "scheduled": "#a78bfa",
    "completed": "#60a5fa",
}
STATUS_LABELS = {
    "running": "\u8fdb\u884c\u4e2d",
    "pending": "\u5f85\u5904\u7406",
    "scheduled": "\u5b9a\u65f6",
    "completed": "\u5b8c\u6210",
}
STATUS_LABELS_EN = {
    "running": "Active", "pending": "Pending", "scheduled": "Scheduled", "completed": "Done",
}
STATUS_TOOLTIPS = {
    "running": "进行中 = 项目今天有活动且距最后活动不超过 2 小时",
    "pending": "待处理 = 项目今天有活动，但距最后活动已超过 2 小时",
    "scheduled": "定时 = 本机 ~/.codex/automations 中当前启用的自动任务",
    "completed": "完成 = 项目所有线程超过 5 天没有新对话",
}
STATUS_TOOLTIPS_EN = {
    "running": "Active = project activity today, within the last 2 hours",
    "pending": "Pending = project activity today, but last activity was over 2 hours ago",
    "scheduled": "Scheduled = enabled tasks in local ~/.codex/automations",
    "completed": "Done = project threads with no new activity for 5+ days",
}
EMPTY_LABELS = {
    "running": "当前没有近 2 小时活跃的项目",
    "pending": "今天没有待处理项目",
    "scheduled": "当前没有启用的自动任务",
    "completed": "没有超过 5 天无活动的项目",
}
EMPTY_LABELS_EN = {
    "running": "No projects active in the last 2 hours",
    "pending": "No pending projects today",
    "scheduled": "No enabled automations",
    "completed": "No projects idle for 5+ days",
}
RUNTIME_BADGE = {
    RuntimeScope.CODEX: ("C", "#60a5fa"),
    RuntimeScope.CLAUDE_CODE: ("H", "#a78bfa"),
}

STATUS_PRIORITY = {"running": 0, "pending": 1, "scheduled": 2, "completed": 3}
SCHEDULED_PROJECT = "自动任务"


def aggregate_tasks_by_project(tasks):
    """按 Runtime + 项目聚合。

    进行中: 今天有活动 + 距最后活动 ≤ 2h
    待处理: 今天有活动 + 距最后活动 > 2h
    完成:   项目超过 _COMPLETED_DAYS 天没有新对话
    单线程对话（空工作目录）排除在统计之外。
    """
    from app.data.codex_reader import _COMPLETED_DAYS
    from app.utils.statistics_timezone import get_statistics_timezone
    from datetime import datetime, timezone

    now_utc = datetime.now(timezone.utc)
    statistics = get_statistics_timezone()
    today = statistics.date_for(now_utc)

    # Group all threads by (runtime, project)
    project_data: dict[tuple, dict] = {}
    for task in tasks or []:
        if getattr(task, "is_single_thread", False):
            continue
        project_name = str(task.project or "").strip()
        if not project_name:
            if task.status == "scheduled":
                project_name = SCHEDULED_PROJECT
            else:
                continue
        key = (task.runtime, project_name.casefold())
        if key not in project_data:
            project_data[key] = {"name": project_name, "items": [], "inactive_items": []}
        if task.status == "inactive":
            project_data[key]["inactive_items"].append(task)
        else:
            project_data[key]["items"].append(task)

    aggregated = []
    for (runtime, _), data in project_data.items():
        items = data["items"]
        inactive_items = data["inactive_items"]
        all_items = items + inactive_items
        all_threads_activity = [t.updated_at for t in all_items if t.updated_at]
        if not all_threads_activity and not any(item.status == "scheduled" for item in items):
            continue
        latest = max(all_threads_activity) if all_threads_activity else None

        if items:
            # Has today-active threads → running or pending
            latest_today = max(items, key=lambda item: item.updated_at.timestamp() if item.updated_at else float("-inf"))
            status = min((item.status for item in items), key=lambda value: STATUS_PRIORITY.get(value, 99))
            latest_title = str(latest_today.title or "").strip()
            aggregated.append(TaskItem(
                id=latest_today.id,
                title=data["name"],
                status=status,
                runtime=runtime,
                updated_at=latest,
                project=data["name"],
                detail=latest_title if latest_title.casefold() != data["name"].casefold() else "",
                thread_count=len(items),
                session_id=latest_today.session_id,
                next_run_at=latest_today.next_run_at,
            ))
        else:
            # No today activity → check if completed (>5d)
            latest_date = get_statistics_timezone().date_for(latest)
            days_since = (today - latest_date).days
            if days_since >= _COMPLETED_DAYS:
                latest_inactive = max(inactive_items, key=lambda item: item.updated_at.timestamp() if item.updated_at else float("-inf"))
                latest_title = str(latest_inactive.title or "").strip()
                aggregated.append(TaskItem(
                    id=latest_inactive.id,
                    title=data["name"],
                    status="completed",
                    runtime=runtime,
                    updated_at=latest,
                    project=data["name"],
                    detail=latest_title if latest_title.casefold() != data["name"].casefold() else "",
                    thread_count=len(inactive_items),
                    session_id=latest_inactive.session_id,
                ))

    return sorted(
        aggregated,
        key=lambda item: (
            STATUS_PRIORITY.get(item.status, 99),
            -(item.updated_at.timestamp() if item.updated_at else 0),
            item.title.casefold(),
        ),
    )


class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self):
        available = max(20, self.width() - 2)
        self.setText(QFontMetrics(self.font()).elidedText(self._full_text, Qt.TextElideMode.ElideRight, available))


class TaskCard(QFrame):
    def __init__(self, task: TaskItem, language="zh", parent=None):
        super().__init__(parent)
        self.setObjectName("taskCard")
        self._task = task
        self._language = language
        self.setFixedHeight(96)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor) if _has_valid_link(task) else QCursor(Qt.CursorShape.ArrowCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = ElidedLabel(task.title or "未命名项目")
        title.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        header.addWidget(title, 1)
        badge_char, badge_color = RUNTIME_BADGE.get(task.runtime, ("?", "#888"))
        badge = QLabel(badge_char)
        badge.setFixedSize(20, 20)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        badge.setStyleSheet(f"background: {badge_color}; color: #fff; border-radius: 10px;")
        header.addWidget(badge)
        layout.addLayout(header)

        if language == "en":
            detail = task.detail or ("Enabled automation" if task.status == "scheduled" else "Project activity today")
        else:
            detail = task.detail or ("启用中的自动任务" if task.status == "scheduled" else "今日项目活动")
        detail_label = ElidedLabel(detail)
        detail_label.setFont(QFont(FONT, 8))
        detail_label.setObjectName("caption")
        layout.addWidget(detail_label)

        status_row = QHBoxLayout()
        status_dot = QLabel()
        status_dot.setFixedSize(8, 8)
        sc = STATUS_COLORS.get(task.status, "#888")
        status_dot.setStyleSheet(f"background: {sc}; border-radius: 4px;")
        status_row.addWidget(status_dot)
        labels = STATUS_LABELS_EN if language == "en" else STATUS_LABELS
        status_text = QLabel(labels.get(task.status, task.status))
        status_text.setFont(QFont(FONT, 8))
        status_text.setStyleSheet(f"color: {sc};")
        status_row.addWidget(status_text)
        count_text = (
            f"{task.thread_count} threads" if language == "en"
            else f"{task.thread_count} 条线程"
        )
        count_label = QLabel(count_text)
        count_label.setFont(QFont(FONT, 8))
        count_label.setObjectName("caption")
        status_row.addWidget(count_label)
        status_row.addStretch()

        if task.status == "scheduled" and task.next_run_at:
            next_local = get_statistics_timezone().datetime_for(task.next_run_at)
            next_text = next_local.strftime("%H:%M") if language == "en" else f"下次 {next_local.strftime('%H:%M')}"
            next_label = QLabel(next_text)
            next_label.setFont(QFont(FONT, 8))
            next_label.setObjectName("caption")
            status_row.addWidget(next_label)
        elif task.updated_at:
            local_time = get_statistics_timezone().datetime_for(task.updated_at)
            time_label = QLabel(local_time.strftime("%H:%M"))
            time_label.setFont(QFont(FONT, 8))
            time_label.setObjectName("caption")
            status_row.addWidget(time_label)
        layout.addLayout(status_row)

        if _has_valid_link(task):
            self.mouseReleaseEvent = self._on_click

    def _on_click(self, event):
        url = _session_url(self._task)
        if url:
            webbrowser.open(url)


class TaskColumn(QFrame):
    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        self.language = "zh"
        color = STATUS_COLORS.get(status, "#888")
        self.setObjectName("subtleCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)

        header = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        header.addWidget(dot)
        self.label = QLabel(STATUS_LABELS.get(status, status))
        self.label.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        self.label.setStyleSheet(f"color: {color};")
        self.label.setToolTip(STATUS_TOOLTIPS.get(status, ""))
        header.addWidget(self.label)
        self.count_label = QLabel("0")
        self.count_label.setFont(QFont(FONT, 10))
        self.count_label.setStyleSheet(f"color: {color};")
        header.addWidget(self.count_label)
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container_layout.setSpacing(4)
        scroll.setWidget(self.container)
        layout.addWidget(scroll, 1)

    def update_tasks(self, tasks):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        filtered = [t for t in tasks if t.status == self.status]
        self.count_label.setText(str(len(filtered)))
        for task in filtered:
            self.container_layout.addWidget(TaskCard(task, self.language))
        if not filtered:
            labels = EMPTY_LABELS_EN if self.language == "en" else EMPTY_LABELS
            empty = QLabel(labels.get(self.status, "No tasks" if self.language == "en" else "当前没有任务"))
            empty.setFont(QFont(FONT, 9))
            empty.setObjectName("caption")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.container_layout.addWidget(empty)

    def set_language(self, language):
        self.language = language
        labels = STATUS_LABELS_EN if language == "en" else STATUS_LABELS
        tooltips = STATUS_TOOLTIPS_EN if language == "en" else STATUS_TOOLTIPS
        self.label.setText(labels.get(self.status, self.status))
        self.label.setToolTip(tooltips.get(self.status, ""))


class TaskBoardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskBoard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.columns = {}
        for i, status in enumerate(["running", "pending", "scheduled", "completed"]):
            col = TaskColumn(status)
            self.columns[status] = col
            grid.addWidget(col, 0, i)
        layout.addLayout(grid, 1)
        self._tasks = []

    def update_tasks(self, tasks):
        self._tasks = aggregate_tasks_by_project(tasks)
        for col in self.columns.values():
            col.update_tasks(self._tasks)

    def project_count(self):
        return len(self._tasks)

    def set_language(self, language):
        for col in self.columns.values():
            col.set_language(language)
            col.update_tasks(self._tasks)


def _is_uuid(value: str) -> bool:
    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value.strip().lower()))


def _has_valid_link(task: TaskItem) -> bool:
    if task.status == "scheduled":
        return False
    session_id = (task.session_id or "").strip().lower()
    return _is_uuid(session_id)


def _session_url(task: TaskItem) -> str:
    session_id = (task.session_id or "").strip().lower()
    if not _is_uuid(session_id):
        return ""
    return f"codex://threads/{session_id}"
