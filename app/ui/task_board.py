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
RUNTIME_BADGE = {
    RuntimeScope.CODEX: ("C", "#60a5fa"),
    RuntimeScope.CLAUDE_CODE: ("H", "#a78bfa"),
}


class TaskCard(QFrame):
    def __init__(self, task: TaskItem, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "TaskCard { background: rgba(255,255,255,0.07); border-radius: 10px; padding: 10px; }"
            "TaskCard:hover { background: rgba(255,255,255,0.12); }"
        )
        self.setFixedHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        id_label = QLabel(task.id[:8] if len(task.id) > 8 else task.id)
        id_label.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        id_label.setStyleSheet("color: #e0e0e0;")
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

        if task.project:
            proj = QLabel(task.project[:30])
            proj.setFont(QFont(FONT, 8))
            proj.setStyleSheet("color: #888;")
            proj.setWordWrap(True)
            layout.addWidget(proj)

        status_row = QHBoxLayout()
        status_dot = QLabel()
        status_dot.setFixedSize(8, 8)
        sc = STATUS_COLORS.get(task.status, "#888")
        status_dot.setStyleSheet(f"background: {sc}; border-radius: 4px;")
        status_row.addWidget(status_dot)
        status_text = QLabel(STATUS_LABELS.get(task.status, task.status))
        status_text.setFont(QFont(FONT, 8))
        status_text.setStyleSheet(f"color: {sc};")
        status_row.addWidget(status_text)
        status_row.addStretch()
        if task.updated_at:
            time_label = QLabel(task.updated_at.strftime("%H:%M"))
            time_label.setFont(QFont(FONT, 8))
            time_label.setStyleSheet("color: #666;")
            status_row.addWidget(time_label)
        layout.addLayout(status_row)


class TaskColumn(QWidget):
    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        color = STATUS_COLORS.get(status, "#888")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        header.addWidget(dot)
        label = QLabel(STATUS_LABELS.get(status, status))
        label.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {color};")
        header.addWidget(label)
        self.count_label = QLabel("0")
        self.count_label.setFont(QFont(FONT, 10))
        self.count_label.setStyleSheet(f"color: {color};")
        header.addWidget(self.count_label)
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; }"
            "QScrollBar::handle:vertical { background: #333; border-radius: 2px; }"
        )
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
            self.container_layout.addWidget(TaskCard(task))
        if not filtered:
            empty = QLabel("\u6682\u65e0")
            empty.setFont(QFont(FONT, 9))
            empty.setStyleSheet("color: #555;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.container_layout.addWidget(empty)


class TaskBoardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("\u2630 \u4eca\u65e5\u4efb\u52a1")
        title.setFont(QFont(FONT, 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        header.addWidget(title)
        header.addStretch()
        self.info_label = QLabel("0 \u4e8b\u9879")
        self.info_label.setFont(QFont(FONT, 10))
        self.info_label.setStyleSheet("color: #888;")
        header.addWidget(self.info_label)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.columns = {}
        for i, status in enumerate(["running", "pending", "scheduled", "completed"]):
            col = TaskColumn(status)
            self.columns[status] = col
            grid.addWidget(col, 0, i)
        layout.addLayout(grid, 1)

    def update_tasks(self, tasks):
        for col in self.columns.values():
            col.update_tasks(tasks)
        self.info_label.setText(f"{len(tasks)} \u4e8b\u9879")
