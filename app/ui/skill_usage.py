from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.data.models import SkillUsage, ToolUsage


class _UsageList(QFrame):
    def __init__(self, title: str, source: str, empty_text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("surfaceCard")
        self.empty_text = empty_text
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        header.addWidget(self.title_label)
        header.addStretch()
        self.source_label = QLabel(source)
        self.source_label.setObjectName("caption")
        header.addWidget(self.source_label)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(7)
        self.rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.container)
        outer.addWidget(scroll, 1)

    def set_items(self, items, value_getter, suffix: str):
        while self.rows.count():
            child = self.rows.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if not items:
            empty = QLabel(self.empty_text)
            empty.setObjectName("caption")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(120)
            self.rows.addWidget(empty)
            return

        maximum = max(value_getter(item) for item in items) or 1
        for rank, item in enumerate(items[:20], 1):
            row = QFrame()
            row.setObjectName("usageRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(10, 7, 10, 7)
            row_layout.setSpacing(5)
            line = QHBoxLayout()
            index = QLabel(f"{rank:02d}")
            index.setObjectName("caption")
            index.setFixedWidth(24)
            line.addWidget(index)
            name = QLabel(item.name)
            name.setObjectName("metricLabel")
            name.setToolTip(item.name)
            line.addWidget(name, 1)
            category = getattr(item, "category", "")
            detail = f"{value_getter(item):,} {suffix}"
            if category:
                detail += f"  ·  {category}"
            value = QLabel(detail)
            value.setObjectName("caption")
            line.addWidget(value)
            row_layout.addLayout(line)
            bar = QProgressBar()
            bar.setRange(0, maximum)
            bar.setValue(value_getter(item))
            bar.setTextVisible(False)
            bar.setFixedHeight(5)
            row_layout.addWidget(bar)
            self.rows.addWidget(row)


class SkillUsageWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.skills = _UsageList(
            "Skill 使用 TOP20",
            "明确 SKILL.md 加载",
            "未发现明确的 Skill 加载记录\n不会把已安装 Skill 或普通文本提及算作使用",
        )
        self.tools = _UsageList(
            "工具调用 TOP20",
            "函数调用事件",
            "未发现明确的工具调用事件",
        )
        layout.addWidget(self.skills, 1)
        layout.addWidget(self.tools, 1)
        self._skills_data = []
        self._tools_data = []
        self.language = "zh"
        self.set_language("zh")

    def set_language(self, language):
        self.language = language
        english = language == "en"
        self.skills.title_label.setText("Top Skills" if english else "Skill 使用 TOP20")
        self.skills.source_label.setText("Usage records" if english else "使用记录")
        self.skills.empty_text = "No skill usage" if english else "暂无 Skill 使用记录"
        self.tools.title_label.setText("Top Tools" if english else "工具调用 TOP20")
        self.tools.source_label.setText("Call records" if english else "调用记录")
        self.tools.empty_text = "No tool calls" if english else "暂无工具调用记录"
        self.set_data(self._skills_data, self._tools_data)

    def set_data(self, skills: list[SkillUsage], tools: list[ToolUsage]):
        self._skills_data = list(skills or [])
        self._tools_data = list(tools or [])
        suffix = "calls" if self.language == "en" else "次"
        self.skills.set_items(self._skills_data, lambda item: item.use_count, suffix)
        self.tools.set_items(self._tools_data, lambda item: item.call_count, suffix)
