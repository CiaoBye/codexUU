from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTabWidget, QWidget, QCheckBox,
    QGroupBox, QFormLayout, QFrame,
)

from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager

FONT = "Microsoft YaHei"


def _combo(items):
    combo = QComboBox()
    combo.addItems(items)
    combo.setStyleSheet(
        "QComboBox { background: rgba(255,255,255,0.08); color: #e0e0e0;"
        "border: 1px solid #444; border-radius: 4px; padding: 5px 10px; min-width: 140px; }"
        "QComboBox::drop-down { border: none; }"
        "QComboBox QAbstractItemView { background: #1e1e3a; color: #e0e0e0;"
        "selection-background-color: rgba(96,165,250,0.4); }"
    )
    return combo


def _cb(text, checked=False):
    cb = QCheckBox(text)
    cb.setChecked(checked)
    cb.setStyleSheet("color: #bbb; spacing: 6px;")
    return cb


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_manager: SettingsManager = None, 
                 translation_manager: TranslationManager = None, 
                 theme_manager: ThemeManager = None):
        super().__init__(parent)
        self.settings_manager = settings_manager or SettingsManager(Path.home() / ".codexU" / "config.json")
        self.translation_manager = translation_manager or TranslationManager()
        self.theme_manager = theme_manager or ThemeManager()
        
        # Connect signals
        self.settings_manager.add_listener(self._on_settings_changed)
        self.translation_manager.add_listener(self._on_language_changed)
        self.theme_manager.add_listener(self._on_theme_changed)
        
        self.setWindowTitle("codexU \u8bbe\u7f6e")
        self.setFixedSize(520, 560)
        self.setStyleSheet(
            "QDialog { background: #1e1e3a; color: #e0e0e0; }"
            "QLabel { color: #ccc; }"
            "QGroupBox { color: #fff; border: 1px solid #333; border-radius: 8px;"
            "margin-top: 12px; padding-top: 16px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { background: rgba(255,255,255,0.03); border: 1px solid #333;"
            "border-radius: 8px; padding: 12px; }"
            "QTabBar::tab { background: rgba(255,255,255,0.06); color: #888;"
            "padding: 8px 16px; margin-right: 4px; border-radius: 6px 6px 0 0; }"
            "QTabBar::tab:selected { background: rgba(96,165,250,0.3); color: #fff; }"
        )

        tabs.addTab(self._general_tab(), "\u901a\u7528")
        tabs.addTab(self._display_tab(), "\u5916\u89c2")
        tabs.addTab(self._system_tab(), "\u7cfb\u7edf")
        layout.addWidget(tabs, 1)

        close_btn = QPushButton("\u5173\u95ed")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(96,165,250,0.4); color: #fff; border: none;"
            "border-radius: 6px; padding: 0 24px; font-weight: bold; }"
            "QPushButton:hover { background: rgba(96,165,250,0.6); }"
        )
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _general_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(14)
        
        # Language combo with signal connection
        lang_combo = _combo(["\u4e2d\u6587", "English"])
        lang_combo.setCurrentIndex(0 if self.translation_manager.get_language() == "zh" else 1)
        lang_combo.currentIndexChanged.connect(self._on_language_changed)
        form.addRow("\u8bed\u8a00:", lang_combo)
        
        form.addRow(_cb("\u81ea\u52a8\u68c0\u67e5 GitHub Release \u66f4\u65b0", True))
        form.addRow(_cb("\u63a5\u6536 Beta \u7248\u672c", True))
        return tab

    def _display_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(14)
        
        # Theme combo with signal connection
        theme_combo = _combo(["\u81ea\u52a8", "\u6d45\u8272", "\u6df1\u8272"])
        theme_map = {"auto": 0, "light": 1, "dark": 2}
        theme_combo.setCurrentIndex(theme_map.get(self.theme_manager.get_theme(), 2))
        theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        form.addRow("\u5916\u89c2:", theme_combo)
        
        grp = QGroupBox("\u72b6\u6001\u680f")
        gl = QVBoxLayout(grp)
        gl.addWidget(QLabel("\u5c55\u793a\u6a21\u5f0f"))
        gl.addWidget(_combo(["\u7b80\u7ea6", "\u7ecf\u5178", "\u4e30\u5bcc"]))
        gl.addWidget(QLabel("\u989d\u5ea6\u53e3\u5f84"))
        gl.addWidget(_combo(["\u5df2\u7528\u91cf", "\u5269\u4f59\u91cf"]))
        gl.addWidget(_cb("\u91cd\u7f6e\u5012\u8ba1\u65f6"))
        gl.addWidget(_cb("\u4e3b\u7a97\u53e3\u7f6e\u9876"))
        gl.addWidget(_cb("\u5173\u95ed\u65f6\u6700\u5c0f\u5316\u5230\u6258\u76d8", True))
        form.addRow(grp)
        return tab

    def _system_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(14)
        status = QLabel("\u8fd0\u884c\u4e2d")
        status.setStyleSheet("color: #22c55e; font-weight: bold;")
        form.addRow("\u7cfb\u7edf\u72b6\u6001:", status)
        form.addRow(_cb("\u81ea\u52a8\u68c0\u67e5\u66f4\u65b0", True))
        btn = QPushButton("\u21bb \u68c0\u67e5\u66f4\u65b0")
        btn.setFixedHeight(30)
        btn.setStyleSheet(
            "QPushButton { background: rgba(96,165,250,0.3); color: #e0e0e0;"
            "border: 1px solid #444; border-radius: 6px; padding: 0 16px; }"
            "QPushButton:hover { background: rgba(96,165,250,0.5); }"
        )
        form.addRow(btn)
        ver = QLabel("v1.0.3")
        ver.setStyleSheet("color: #666;")
        form.addRow("\u7248\u672c:", ver)
        return tab
    
    def _on_language_changed(self, index):
        lang = "zh" if index == 0 else "en"
        self.translation_manager.set_language(lang)
        self.settings_manager.set_language(lang)
        self.settings_manager.save()

    def _on_theme_changed(self, index):
        theme_map = {0: "auto", 1: "light", 2: "dark"}
        theme = theme_map.get(index, "dark")
        self.theme_manager.set_theme(theme)
        self.settings_manager.set_theme(theme)
        self.settings_manager.save()

    def _on_settings_changed(self):
        # Update UI with current settings
        pass
