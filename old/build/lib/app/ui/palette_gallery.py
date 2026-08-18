from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPaintEvent, QPainter
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.utils.palette_manager import PaletteManager, PaletteTokens, PaletteDefinition


def _swatch_widget(color: str, size: int = 24) -> QFrame:
    f = QFrame()
    f.setFixedSize(size, size)
    f.setObjectName("swatch")
    if color:
        f.setStyleSheet(f"QFrame#swatch {{ background: {color}; border-radius: {size//6}px; border: 1px solid rgba(0,0,0,0.12); }}")
    return f


class PaletteCard(QFrame):
    clicked = Signal(str)

    def __init__(self, palette_id: str, name: str, tokens: PaletteTokens, selected: bool, parent=None):
        super().__init__(parent)
        self._pid = palette_id
        self._selected = selected
        self.setFixedSize(160, 120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("paletteCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)

        # Name
        self._label = QLabel(name)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        # Swatch row
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(4)
        swatch_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for key in ("primary", "primaryStrong", "secondary", "secondaryStrong"):
            c = tokens.accent.get(key) if tokens else None
            if c:
                swatch_row.addWidget(_swatch_widget(c, 20))
        if swatch_row.count() == 0:
            swatch_row.addStretch()
        layout.addLayout(swatch_row)

        self._update_style()

    def _update_style(self):
        bg = "#e8e8e8" if self._selected else "#ffffff"
        border = "#1a73e8" if self._selected else "#dadce0"
        self.setStyleSheet(
            f"QFrame#paletteCard {{ background: {bg}; border: 2px solid {border}; border-radius: 8px; }}"
            f"QFrame#paletteCard:hover {{ background: #f0f4ff; border-color: #1a73e8; }}"
            f"QLabel {{ font-size: 12px; }}"
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self._pid)
        super().mousePressEvent(event)


class PaletteGalleryDialog(QDialog):
    palette_selected = Signal(str)

    def __init__(self, palette_manager: PaletteManager, current_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择主题风格")
        self.setMinimumSize(520, 380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._grid = QGridLayout(content)
        self._grid.setSpacing(8)

        palette_ids = palette_manager.palette_ids
        if "codexu.default" in palette_ids:
            palette_ids.insert(0, palette_ids.pop(palette_ids.index("codexu.default")))

        cols = 3
        for i, pid in enumerate(palette_ids):
            definition = palette_manager.get(pid)
            if not definition:
                continue
            name = definition.localized_name("zh-Hans")
            tokens = palette_manager.load_tokens(pid, "light")
            if not tokens:
                tokens = PaletteTokens(pid, "light")
            card = PaletteCard(pid, name, tokens, pid == current_id)
            card.clicked.connect(self._on_card_clicked)
            self._grid.addWidget(card, i // cols, i % cols)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("取消")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_card_clicked(self, pid: str):
        self.palette_selected.emit(pid)
        self.accept()
