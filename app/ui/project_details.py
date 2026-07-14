from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.data.models import ProjectStats, format_tokens


def _period_values(project: ProjectStats, mode: str) -> tuple[int, float, float]:
    if mode == "week":
        return project.current_week_token_total or 0, project.current_week_estimated_value or 0.0, project.current_week_pricing_coverage_pct
    if mode == "month":
        return project.current_month_token_total or 0, project.current_month_estimated_value or 0.0, project.current_month_pricing_coverage_pct
    return project.token_total, project.estimated_value, project.pricing_coverage_pct


def project_export_payload(project: ProjectStats, mode: str) -> dict:
    tokens, value, coverage = _period_values(project, mode)
    return {
        "project": project.name,
        "period": mode,
        "runtime": project.runtime.value,
        "token_total": tokens,
        "estimated_api_value": round(value, 2),
        "pricing_coverage_pct": round(coverage, 1),
        "thread_count": project.thread_count,
        "last_active": project.last_active.isoformat() if project.last_active else None,
        "source": project.source_label,
        "models": [
            {
                "name": item.name,
                "token_total": item.token_total,
                "estimated_api_value": round(item.estimated_value, 2),
                "pricing_coverage_pct": round(item.pricing_coverage_pct, 1),
            }
            for item in project.model_usage
        ],
        "sessions": [
            {
                "session_id": item.session_id,
                "token_total": item.token_total,
                "last_active": item.last_active.isoformat() if item.last_active else None,
                "dominant_model": item.model,
            }
            for item in project.sessions
        ],
    }


def project_markdown(payload: dict) -> str:
    lines = [
        f"# {payload['project']}",
        "",
        f"- 统计口径：{payload['period']}",
        f"- Runtime：{payload['runtime']}",
        f"- Token：{format_tokens(payload['token_total'])}",
        f"- API 等效价值：${payload['estimated_api_value']:.2f}（计价覆盖 {payload['pricing_coverage_pct']:.0f}%）",
        f"- 线程：{payload['thread_count']}",
        "",
        "## 模型拆分",
        "",
        "| 模型 | Token | API 等效价值 | 覆盖率 |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {item['name']} | {format_tokens(item['token_total'])} | ${item['estimated_api_value']:.2f} | {item['pricing_coverage_pct']:.0f}% |"
        for item in payload["models"]
    )
    return "\n".join(lines)


class _DetailRow(QFrame):
    def __init__(self, title: str, subtitle: str, value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("detailRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        name = QLabel(title)
        name.setObjectName("projectName")
        labels.addWidget(name)
        detail = QLabel(subtitle)
        detail.setObjectName("caption")
        labels.addWidget(detail)
        layout.addLayout(labels, 1)
        amount = QLabel(value)
        amount.setObjectName("projectToken")
        amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(amount)


class ProjectDetailDialog(QDialog):
    def __init__(self, project: ProjectStats, mode: str, english: bool = False, parent=None):
        super().__init__(parent)
        self.project = project
        self.mode = mode
        self.english = english
        self.payload = project_export_payload(project, mode)
        self.setObjectName("projectDetailDialog")
        self.setWindowTitle(("Project details · " if english else "项目详情 · ") + (project.name or "default"))
        self.setMinimumSize(760, 520)
        self.resize(860, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(project.name or "default")
        title.setObjectName("pageTitle")
        title_box.addWidget(title)
        period = {"week": "本周", "month": "本月", "all": "累计"}.get(mode, mode)
        if english:
            period = {"week": "This week", "month": "This month", "all": "All time"}.get(mode, mode)
        subtitle = QLabel(
            f"{period} · {project.source_label or ('Detailed' if english else '精细统计')}"
        )
        subtitle.setObjectName("caption")
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch()
        for text, handler, style in (
            ("Export JSON" if english else "导出 JSON", self._export_json, "iconButton"),
            ("Export CSV" if english else "导出 CSV", self._export_csv, "iconButton"),
            ("Copy Markdown" if english else "复制 Markdown", self._copy_markdown, "primaryButton"),
        ):
            button = QPushButton(text)
            button.setObjectName(style)
            button.clicked.connect(handler)
            heading.addWidget(button)
        root.addLayout(heading)

        tokens, value, coverage = _period_values(project, mode)
        summary = QFrame()
        summary.setObjectName("statStrip")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        for label, amount in (
            ("Token", format_tokens(tokens)),
            ("API value" if english else "API 等效价值", f"${value:.2f}"),
            ("Coverage" if english else "计价覆盖", f"{coverage:.0f}%"),
            ("Sessions" if english else "会话", str(len(project.sessions))),
        ):
            box = QVBoxLayout()
            number = QLabel(amount)
            number.setObjectName("overviewValue")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(number)
            caption = QLabel(label)
            caption.setObjectName("caption")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(caption)
            summary_layout.addLayout(box, 1)
        root.addWidget(summary)

        content = QHBoxLayout()
        content.setSpacing(12)
        models = QFrame()
        models.setObjectName("surfaceCard")
        model_layout = QVBoxLayout(models)
        model_layout.setContentsMargins(13, 11, 13, 11)
        model_layout.addWidget(QLabel("Model breakdown" if english else "模型拆分", objectName="sectionTitle"))
        model_scroll, self.model_layout = self._scroll_column()
        model_layout.addWidget(model_scroll, 1)
        content.addWidget(models, 4)

        sessions = QFrame()
        sessions.setObjectName("surfaceCard")
        session_layout = QVBoxLayout(sessions)
        session_layout.setContentsMargins(13, 11, 13, 11)
        session_header = QHBoxLayout()
        session_header.addWidget(QLabel("Sessions" if english else "会话浏览", objectName="sectionTitle"))
        session_header.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter sessions…" if english else "筛选会话…")
        self.search.setFixedWidth(180)
        self.search.textChanged.connect(self._render_sessions)
        session_header.addWidget(self.search)
        session_layout.addLayout(session_header)
        session_scroll, self.session_layout = self._scroll_column()
        session_layout.addWidget(session_scroll, 1)
        content.addWidget(sessions, 6)
        root.addLayout(content, 1)
        self._render_models()
        self._render_sessions()

    @staticmethod
    def _scroll_column():
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        return scroll, layout

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_models(self):
        self._clear(self.model_layout)
        for model in self.project.model_usage:
            priced = f"${model.estimated_value:.2f} · {model.pricing_coverage_pct:.0f}%"
            self.model_layout.addWidget(_DetailRow(model.name, priced, format_tokens(model.token_total)))
        if not self.project.model_usage:
            self.model_layout.addWidget(QLabel("No model records" if self.english else "暂无模型记录", objectName="caption"))

    def _render_sessions(self):
        self._clear(self.session_layout)
        keyword = self.search.text().strip().lower()
        sessions = [
            item for item in self.project.sessions
            if not keyword or keyword in item.session_id.lower() or keyword in item.model.lower()
        ]
        for session in sessions:
            active = session.last_active.strftime("%m/%d %H:%M") if session.last_active else "--"
            subtitle = f"{session.model} · {active}"
            self.session_layout.addWidget(_DetailRow(session.session_id, subtitle, format_tokens(session.token_total)))
        if not sessions:
            self.session_layout.addWidget(QLabel("No matching sessions" if self.english else "没有匹配的会话", objectName="caption"))

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", f"{self.project.name or 'project'}.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(self.payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"{self.project.name or 'project'}-sessions.csv", "CSV (*.csv)")
        if not path:
            return
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("session_id", "token_total", "last_active", "dominant_model"))
            writer.writeheader()
            writer.writerows(self.payload["sessions"])

    def _copy_markdown(self):
        QApplication.clipboard().setText(project_markdown(self.payload))
