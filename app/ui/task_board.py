from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QGridLayout,
)

from app.data.models import TaskItem, RuntimeScope

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
EMPTY_LABELS = {
    "running": "当前没有近 2 小时活跃的线程",
    "pending": "今天没有待处理线程",
    "scheduled": "当前没有启用的自动任务",
    "completed": "今天没有归档的线程",
}
EMPTY_LABELS_EN = {
    "running": "No threads active in the last 2 hours",
    "pending": "No pending threads today",
    "scheduled": "No enabled automations",
    "completed": "No threads archived today",
}
RUNTIME_BADGE = {
    RuntimeScope.CODEX: ("C", "#60a5fa"),
    RuntimeScope.CLAUDE_CODE: ("H", "#a78bfa"),
}


class TaskCard(QFrame):
    def __init__(self, task: TaskItem, language="zh", parent=None):
        super().__init__(parent)
        self.setObjectName("taskCard")
        self.setFixedHeight(92)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        id_label = QLabel(task.id[:8] if len(task.id) > 8 else task.id)
        id_label.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        id_label.setObjectName("caption")
        header.addWidget(id_label)
        header.addStretch()
        badge_char, badge_color = RUNTIME_BADGE.get(task.runtime, ("?", "#888"))
        badge = QLabel(badge_char)
        badge.setFixedSize(20, 20)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        badge.setStyleSheet(f"background: {badge_color}; color: #fff; border-radius: 10px;")
        header.addWidget(badge)
        layout.addLayout(header)

        title = QLabel(task.title or "未命名任务")
        title.setWordWrap(False)
        title.setToolTip(task.title or "未命名任务")
        title.setStyleSheet("font-size: 12px; font-weight: 600;")
        layout.addWidget(title)

        if task.project:
            proj = QLabel(task.project[:30])
            proj.setFont(QFont(FONT, 8))
            proj.setObjectName("caption")
            proj.setWordWrap(True)
            layout.addWidget(proj)

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
        status_row.addStretch()
        if task.updated_at:
            time_label = QLabel(task.updated_at.strftime("%H:%M"))
            time_label.setFont(QFont(FONT, 8))
            time_label.setObjectName("caption")
            status_row.addWidget(time_label)
        layout.addLayout(status_row)


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
        if status == "completed":
            self.label.setToolTip("完成 = 今天在 Codex 中归档的线程")
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
        self.label.setText(labels.get(self.status, self.status))
        if self.status == "completed":
            self.label.setToolTip(
                "Done = threads archived in Codex today"
                if language == "en" else "完成 = 今天在 Codex 中归档的线程"
            )


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
        self._tasks = list(tasks or [])
        for col in self.columns.values():
            col.update_tasks(self._tasks)

    def set_language(self, language):
        for col in self.columns.values():
            col.set_language(language)
            col.update_tasks(self._tasks)
