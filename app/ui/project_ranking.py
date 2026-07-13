from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy,
)

from app.data.models import ProjectStats, format_tokens

FONT = "Microsoft YaHei"


class ProjectRow(QFrame):
    def __init__(self, project: ProjectStats, rank: int, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "ProjectRow { background: rgba(255,255,255,0.03); border-radius: 6px; padding: 4px; margin: 1px; }"
            "ProjectRow:hover { background: rgba(255,255,255,0.08); }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        rank_label = QLabel(f"#{rank}")
        rank_label.setFont(QFont(FONT, 9, QFont.Weight.Bold))
        rank_label.setFixedWidth(28)
        rank_label.setStyleSheet("color: #888;")
        layout.addWidget(rank_label)

        name_label = QLabel(project.name)
        name_label.setFont(QFont(FONT, 10))
        name_label.setStyleSheet("color: #e0e0e0;")
        name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(name_label, 1)

        tokens_label = QLabel(format_tokens(project.token_total))
        tokens_label.setFont(QFont(FONT, 9))
        tokens_label.setStyleSheet("color: #aaa;")
        tokens_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(tokens_label)

        if project.estimated_value > 0:
            value_label = QLabel(f"${project.estimated_value:.2f}")
            value_label.setFont(QFont(FONT, 9))
            value_label.setStyleSheet("color: #888;")
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            value_label.setFixedWidth(70)
            layout.addWidget(value_label)

        count_label = QLabel(f"{project.thread_count}")
        count_label.setFont(QFont(FONT, 9))
        count_label.setStyleSheet("color: #666;")
        count_label.setFixedWidth(30)
        count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(count_label)


class ProjectRankingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("\u9879\u76ee\u6392\u884c")
        title.setFont(QFont(FONT, 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0; padding: 8px 0;")
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 6px; }"
            "QScrollBar::handle:vertical { background: #444; border-radius: 3px; }"
        )
        self.project_container = QWidget()
        self.project_layout = QVBoxLayout(self.project_container)
        self.project_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.project_layout.setSpacing(2)
        self.scroll.setWidget(self.project_container)
        layout.addWidget(self.scroll)

    def update_projects(self, projects):
        while self.project_layout.count():
            item = self.project_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not projects:
            empty = QLabel("\u6682\u65e0\u9879\u76ee\u6570\u636e")
            empty.setFont(QFont(FONT, 10))
            empty.setStyleSheet("color: #666; padding: 20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.project_layout.addWidget(empty)
            return
        for i, proj in enumerate(projects[:20]):
            self.project_layout.addWidget(ProjectRow(proj, i + 1))
