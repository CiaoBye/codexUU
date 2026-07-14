from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.data.models import format_tokens
from app.utils.statistics_timezone import get_statistics_timezone


def _quota_line(label: str, quota) -> str:
    if quota is None:
        return f"{label} --"
    reset = ""
    if quota.reset_time:
        local_time: datetime = quota.reset_time.astimezone(get_statistics_timezone().tzinfo())
        reset = f" · {local_time.strftime('%m/%d %H:%M')}"
    return f"{label} {quota.remaining_pct:.0f}%{reset}"


class DesktopStatusPanel(QWidget):
    """可拖动的桌面状态窗；只显示本机可验证状态。"""

    show_main = Signal()
    hide_requested = Signal()
    position_changed = Signal(QPoint)

    def __init__(self, parent=None):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(parent, flags)
        self.setObjectName("desktopStatusPanel")
        self.setFixedSize(318, 142)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._drag_start: QPoint | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("desktopStatusShell")
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        logo = QLabel()
        icon_path = Path(__file__).resolve().parents[1] / "resources" / "icons" / "codexu-logo.svg"
        logo.setPixmap(QPixmap(str(icon_path)).scaled(22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.runtime = QLabel("Codex")
        self.runtime.setObjectName("projectName")
        title_box.addWidget(self.runtime)
        source = QLabel("本机桌面状态")
        source.setObjectName("caption")
        title_box.addWidget(source)
        header.addLayout(title_box)
        header.addStretch()
        open_button = QPushButton("打开")
        open_button.setObjectName("desktopStatusButton")
        open_button.clicked.connect(self.show_main.emit)
        header.addWidget(open_button)
        hide_button = QPushButton("隐藏")
        hide_button.setObjectName("desktopStatusButton")
        hide_button.clicked.connect(self.hide_requested.emit)
        header.addWidget(hide_button)
        layout.addLayout(header)

        self.today = QLabel("今日 0")
        self.today.setObjectName("desktopStatusValue")
        layout.addWidget(self.today)
        self.quota = QLabel("5h --    7d --")
        self.quota.setObjectName("desktopStatusQuota")
        layout.addWidget(self.quota)
        note = QLabel("拖动窗口可调整位置")
        note.setObjectName("caption")
        layout.addWidget(note)
        root.addWidget(shell)

    def update_snapshot(self, runtime: str, snapshot):
        self.runtime.setText("Claude Code" if runtime == "claudeCode" else "Codex")
        self.today.setText(f"今日 {format_tokens(snapshot.tokens.today.total)}")
        self.quota.setText(f"{_quota_line('5h', snapshot.quota_5h)}    {_quota_line('7d', snapshot.quota_7d)}")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self.position_changed.emit(self.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
