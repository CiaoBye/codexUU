from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListView, QMessageBox, QPushButton, QScrollArea, QStyledItemDelegate, QTabWidget, QDoubleSpinBox,
    QVBoxLayout, QWidget, QApplication,
)

from app.constants import APP_REPO, APP_VERSION
from app.data.local_index import clear_local_index, local_index_status
from app.utils.data_diagnostics import diagnose_data_sources
from app.utils.global_hotkey import parse_shortcut
from app.utils.settings import SettingsManager
from app.utils.statistics_timezone import DEFAULT_FIXED_ZONE, configure_statistics_timezone
from app.utils.theme import ThemeManager
from app.utils.translation import TranslationManager
from app.utils.update_checker import check_for_update


ICONS_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons"


class _ComboDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(34, size.height()))


class StyledComboBox(QComboBox):
    """统一使用 Qt 自绘列表，避开 Windows 原生下拉框的方框和箭头。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView(self)
        view.setObjectName("comboPopup")
        view.setSpacing(2)
        view.setUniformItemSizes(True)
        view.setItemDelegate(_ComboDelegate(view))
        self.setView(view)
        self.setMaxVisibleItems(7)

    def wheelEvent(self, event):
        # 设置项只允许通过点击后选择，避免滚轮经过时误改配置。
        event.ignore()


class ShortcutRecorder(QPushButton):
    sequence_changed = Signal(str)

    def __init__(self, sequence: str, parent=None):
        super().__init__(parent)
        self._sequence = sequence
        self._recording = False
        self.setObjectName("shortcutRecorder")
        self.setMinimumHeight(36)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self.begin_recording)
        self._render()

    def sequence(self):
        return self._sequence

    def set_sequence(self, sequence):
        self._sequence = str(sequence or "Ctrl+U")
        self._recording = False
        self._render()

    def begin_recording(self):
        self._recording = True
        self.setText("请按下新的组合键…")
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._finish_recording()
            return
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            return
        modifiers = []
        pressed = event.modifiers()
        for flag, label in (
            (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
            (Qt.KeyboardModifier.AltModifier, "Alt"),
            (Qt.KeyboardModifier.ShiftModifier, "Shift"),
            (Qt.KeyboardModifier.MetaModifier, "Win"),
        ):
            if pressed & flag:
                modifiers.append(label)
        key_text = QKeySequence(event.key()).toString(QKeySequence.SequenceFormat.PortableText)
        candidate = "+".join(modifiers + [key_text])
        if parse_shortcut(candidate):
            self._sequence = candidate
            self._finish_recording()
            self.sequence_changed.emit(candidate)

    def focusOutEvent(self, event):
        if self._recording:
            self._finish_recording()
        super().focusOutEvent(event)

    def _finish_recording(self):
        if self._recording:
            self.releaseKeyboard()
        self._recording = False
        self._render()

    def _render(self):
        self.setText(f"{self._sequence}    ·    点击重新录制")


def _combo(items):
    combo = StyledComboBox()
    combo.addItems(items)
    return combo


def _check(text: str, checked: bool = False):
    box = QCheckBox(text)
    box.setChecked(checked)
    return box


class _UpdateWorker(QObject):
    finished = Signal(object)

    def __init__(self, current_version: str, include_beta: bool):
        super().__init__()
        self.current_version = current_version
        self.include_beta = include_beta

    def run(self):
        self.finished.emit(check_for_update(self.current_version, self.include_beta, force=True))


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_manager: SettingsManager = None,
                 translation_manager: TranslationManager = None,
                 theme_manager: ThemeManager = None):
        super().__init__(parent)
        self.settings_manager = settings_manager or SettingsManager(Path.home() / ".codexU" / "config.json")
        self.translation_manager = translation_manager or TranslationManager()
        self.theme_manager = theme_manager or ThemeManager()
        self._update_thread = None
        self._update_worker = None
        self._latest_release = None
        self._settings_dirty = False

        self.setObjectName("settingsDialog")
        self.setWindowTitle("CodexUU 设置")
        self.setMinimumSize(660, 600)
        self.resize(700, 680)
        self.settings_manager.add_listener(self._on_settings_changed)
        self.translation_manager.add_listener(self._retranslate_ui)
        self.theme_manager.add_listener(self._on_theme_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        heading = QHBoxLayout()
        self.heading_title = QLabel("设置")
        self.heading_title.setObjectName("pageTitle")
        heading.addWidget(self.heading_title)
        heading.addStretch()
        heading.addWidget(QLabel("CodexUU", objectName="caption"))
        root.addLayout(heading)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._general_tab(), "通用")
        self.tabs.addTab(self._display_tab(), "外观")
        self.tabs.addTab(self._system_tab(), "系统")
        for index, icon in enumerate(("settings-general.svg", "settings-display.svg", "settings-system.svg")):
            self.tabs.setTabIcon(index, QIcon(str(ICONS_DIR / icon)))
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("iconButton")
        self.cancel_btn.setMinimumWidth(84)
        self.cancel_btn.clicked.connect(self.reject)
        footer.addWidget(self.cancel_btn)
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setMinimumWidth(104)
        self.save_btn.clicked.connect(self._apply_settings)
        footer.addWidget(self.save_btn)
        root.addLayout(footer)
        self._retranslate_ui()

    def _card(self, title: str):
        card = QGroupBox(title)
        card.setObjectName("surfaceCard")
        layout = QFormLayout(card)
        layout.setContentsMargins(18, 20, 18, 16)
        layout.setVerticalSpacing(14)
        return card, layout

    def _general_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 14, 8, 8)
        self.preference_card, form = self._card("偏好")
        card = self.preference_card
        self.preference_form = form
        self.lang_combo = _combo(["中文", "English"])
        self.lang_combo.setCurrentIndex(0 if self.translation_manager.get_language() == "zh" else 1)
        self.lang_combo.currentIndexChanged.connect(self._on_language_index)
        form.addRow("语言", self.lang_combo)
        self.runtime_combo = StyledComboBox()
        self.runtime_combo.addItem("Codex", "codex")
        self.runtime_combo.addItem("Claude Code", "claudeCode")
        self.runtime_combo.setCurrentIndex(0 if self.settings_manager.get_active_runtime() == "codex" else 1)
        self.runtime_combo.currentIndexChanged.connect(self._on_runtime_index)
        form.addRow("数据源", self.runtime_combo)
        self.auto_update_cb = _check("自动检查 GitHub Release 更新", True)
        self.beta_cb = _check("接收 Beta / prerelease 版本", True)
        auto_update, include_beta = self.settings_manager.get_update_preferences()
        self.auto_update_cb.setChecked(auto_update)
        self.beta_cb.setChecked(include_beta)
        self.auto_update_cb.stateChanged.connect(self._save_update_preferences)
        self.beta_cb.stateChanged.connect(self._save_update_preferences)
        form.addRow(self.auto_update_cb)
        form.addRow(self.beta_cb)
        layout.addWidget(card)

        self.window_card, window_form = self._card("窗口与快捷键")
        self.window_form = window_form
        self.shortcut_row = QWidget()
        shortcut_layout = QHBoxLayout(self.shortcut_row)
        shortcut_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_layout.setSpacing(8)
        self.shortcut_edit = ShortcutRecorder(self.settings_manager.get_shortcut())
        self.shortcut_edit.sequence_changed.connect(self._save_shortcut)
        shortcut_layout.addWidget(self.shortcut_edit, 1)
        self.shortcut_reset = QPushButton("恢复默认")
        self.shortcut_reset.setObjectName("iconButton")
        self.shortcut_reset.clicked.connect(lambda: self._save_shortcut("Ctrl+U"))
        shortcut_layout.addWidget(self.shortcut_reset)
        window_form.addRow("全局快捷键", self.shortcut_row)
        self.shortcut_status = QLabel("")
        self.shortcut_status.setObjectName("caption")
        window_form.addRow("状态", self.shortcut_status)
        always_on_top, close_behavior = self.settings_manager.get_window_preferences()
        self.always_on_top_cb = _check("主窗口始终置顶", always_on_top)
        self.always_on_top_cb.stateChanged.connect(self._save_window_preferences)
        window_form.addRow(self.always_on_top_cb)
        desktop_enabled, _ = self.settings_manager.get_desktop_status_preferences()
        self.desktop_status_cb = _check("在桌面显示状态悬浮窗", desktop_enabled)
        self.desktop_status_cb.stateChanged.connect(self._save_window_preferences)
        window_form.addRow(self.desktop_status_cb)
        self.desktop_style_combo = StyledComboBox()
        self.desktop_style_combo.addItem("信息圆盘 A", "orb")
        self.desktop_style_combo.addItem("双环仪表 A", "halo")
        self.desktop_style_combo.addItem("极简圆环 B", "mini")
        self.desktop_style_combo.addItem("状态胶囊 B", "capsule")
        self.desktop_style_combo.addItem("双轨卡片 B", "tracks")
        self.desktop_style_combo.setCurrentIndex(max(0, self.desktop_style_combo.findData(self.settings_manager.get_desktop_status_style())))
        self.desktop_style_combo.currentIndexChanged.connect(self._save_window_preferences)
        window_form.addRow("桌面悬浮样式", self.desktop_style_combo)
        self.desktop_size_combo = StyledComboBox()
        self.desktop_size_combo.addItem("小", "small")
        self.desktop_size_combo.addItem("中", "medium")
        self.desktop_size_combo.addItem("大", "large")
        self.desktop_size_combo.setCurrentIndex(max(0, self.desktop_size_combo.findData(self.settings_manager.get_desktop_status_size())))
        self.desktop_size_combo.currentIndexChanged.connect(self._save_window_preferences)
        window_form.addRow("悬浮窗大小", self.desktop_size_combo)
        self.desktop_scale_spin = QDoubleSpinBox()
        self.desktop_scale_spin.setRange(20, 300)
        self.desktop_scale_spin.setSingleStep(5)
        self.desktop_scale_spin.setSuffix("%")
        self.desktop_scale_spin.setValue(round(self.settings_manager.get_desktop_status_scale() * 100))
        self.desktop_scale_spin.valueChanged.connect(self._save_window_preferences)
        window_form.addRow("自定义缩放", self.desktop_scale_spin)
        self.lightweight_mode_cb = _check("轻量模式（运行时不显示任务栏图标）", self.settings_manager.get_lightweight_mode())
        self.lightweight_mode_cb.stateChanged.connect(self._save_window_preferences)
        window_form.addRow(self.lightweight_mode_cb)
        self.close_combo = StyledComboBox()
        self.close_combo.addItem("隐藏到托盘", "tray")
        self.close_combo.addItem("最小化", "minimize")
        self.close_combo.addItem("退出程序", "quit")
        self.close_combo.setCurrentIndex(max(0, self.close_combo.findData(close_behavior)))
        self.close_combo.currentIndexChanged.connect(self._save_window_preferences)
        window_form.addRow("关闭主窗口", self.close_combo)
        layout.addWidget(self.window_card)
        layout.addStretch()
        return tab

    def _display_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 14, 8, 8)
        self.appearance_card, form = self._card("外观")
        card = self.appearance_card
        self.appearance_form = form
        self.theme_combo = _combo(["自动", "浅色", "深色"])
        theme_map = {"auto": 0, "light": 1, "dark": 2}
        self.theme_combo.setCurrentIndex(theme_map.get(self.theme_manager.get_theme(), 2))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_index)
        form.addRow("主题", self.theme_combo)
        self.quota_combo = StyledComboBox()
        self.quota_combo.addItem("显示剩余", "remaining")
        self.quota_combo.addItem("显示已用", "used")
        self.quota_combo.setCurrentIndex(0 if self.settings_manager.get_quota_display() == "remaining" else 1)
        self.quota_combo.currentIndexChanged.connect(self._save_display_preferences)
        form.addRow("额度口径", self.quota_combo)
        self.reduce_motion_cb = _check("减少动态效果", self.settings_manager.get_reduce_motion())
        self.reduce_motion_cb.stateChanged.connect(self._save_display_preferences)
        form.addRow(self.reduce_motion_cb)
        self.display_note = QLabel("界面会根据主题自动调整背景、卡片、文字和控件对比度。")
        self.display_note.setObjectName("caption")
        self.display_note.setWordWrap(True)
        form.addRow("说明", self.display_note)
        layout.addWidget(card)
        layout.addStretch()
        return tab

    def _system_tab(self):
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 14, 8, 8)
        self.update_card, update_form = self._card("更新")
        update_card = self.update_card
        self.update_form = update_form
        self.check_update_btn = QPushButton("检查更新")
        self.check_update_btn.setObjectName("primaryButton")
        self.check_update_btn.clicked.connect(self._check_for_update)
        update_form.addRow("当前版本", QLabel(APP_VERSION))
        update_form.addRow("手动检查", self.check_update_btn)
        self.update_status_label = QLabel("尚未检查")
        self.update_status_label.setObjectName("caption")
        self.update_status_label.setWordWrap(True)
        update_form.addRow("状态", self.update_status_label)
        update_actions = QWidget()
        update_actions_layout = QHBoxLayout(update_actions)
        update_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.download_update_btn = QPushButton("下载更新")
        self.download_update_btn.setObjectName("primaryButton")
        self.download_update_btn.setEnabled(False)
        self.download_update_btn.clicked.connect(self._download_update)
        update_actions_layout.addWidget(self.download_update_btn)
        self.open_release_btn = QPushButton("打开 Release")
        self.open_release_btn.setObjectName("iconButton")
        self.open_release_btn.clicked.connect(self._open_release)
        update_actions_layout.addWidget(self.open_release_btn)
        update_form.addRow("新版本", update_actions)
        layout.addWidget(update_card)

        self.timezone_card, timezone_form = self._card("统计口径")
        timezone_card = self.timezone_card
        self.timezone_form = timezone_form
        mode, identifier = self.settings_manager.get_statistics_timezone()
        self.timezone_combo = StyledComboBox()
        self.timezone_combo.addItem("跟随系统", "system")
        self.timezone_combo.addItem("UTC", "utc")
        self.timezone_combo.addItem("固定 IANA 时区", "fixed")
        self.timezone_combo.setCurrentIndex({"system": 0, "utc": 1, "fixed": 2}.get(mode, 0))
        self.timezone_combo.currentIndexChanged.connect(self._on_timezone_index)
        timezone_form.addRow("自然日", self.timezone_combo)
        self.timezone_edit = QLineEdit(identifier or DEFAULT_FIXED_ZONE)
        self.timezone_edit.setPlaceholderText("例如 Asia/Shanghai")
        self.timezone_edit.setEnabled(mode == "fixed")
        self.timezone_edit.editingFinished.connect(self._on_timezone_text_changed)
        timezone_form.addRow("IANA 标识", self.timezone_edit)
        layout.addWidget(timezone_card)

        self.diagnostic_card, diagnostic_form = self._card("数据源诊断")
        self.diagnostic_form = diagnostic_form
        self.diagnostic_label = QLabel()
        self.diagnostic_label.setObjectName("diagnosticText")
        self.diagnostic_label.setWordWrap(True)
        diagnostic_form.addRow(self.diagnostic_label)
        self.data_scope_label = QLabel("所有用量、趋势和项目数字均来自本机记录；不会上传线程正文或项目路径。")
        self.data_scope_label.setObjectName("caption")
        self.data_scope_label.setWordWrap(True)
        diagnostic_form.addRow("统计范围", self.data_scope_label)
        self.diagnostic_button = QPushButton("重新检测")
        self.diagnostic_button.setObjectName("iconButton")
        self.diagnostic_button.clicked.connect(self._refresh_diagnostics)
        diagnostic_form.addRow(self.diagnostic_button)
        layout.addWidget(self.diagnostic_card)

        self.alert_card, alert_form = self._card("额度提醒")
        self.alert_form = alert_form
        self.quota_alert_combo = StyledComboBox()
        for label, value in (("关闭", 0), ("剩余 10%", 10), ("剩余 20%", 20), ("剩余 30%", 30), ("剩余 50%", 50)):
            self.quota_alert_combo.addItem(label, value)
        self.quota_alert_combo.setCurrentIndex(max(0, self.quota_alert_combo.findData(self.settings_manager.get_quota_alert_threshold())))
        self.quota_alert_combo.currentIndexChanged.connect(self._save_quota_alert)
        alert_form.addRow("提醒阈值", self.quota_alert_combo)
        alert_note = QLabel("额度低于阈值时，每个额度窗口在本次重置周期内只通知一次。")
        alert_note.setObjectName("caption")
        alert_note.setWordWrap(True)
        self.alert_note = alert_note
        alert_form.addRow("说明", alert_note)
        layout.addWidget(self.alert_card)

        self.maintenance_card, maintenance_form = self._card("数据维护")
        self.maintenance_form = maintenance_form
        self.index_status_label = QLabel()
        self.index_status_label.setObjectName("caption")
        self.index_status_label.setWordWrap(True)
        maintenance_form.addRow("本机索引", self.index_status_label)
        self.clear_index_btn = QPushButton("清理并在下次读取时重建")
        self.clear_index_btn.setObjectName("iconButton")
        self.clear_index_btn.clicked.connect(self._clear_local_index)
        maintenance_form.addRow("可重建数据", self.clear_index_btn)
        layout.addWidget(self.maintenance_card)
        self._refresh_diagnostics()
        self._refresh_index_maintenance()
        layout.addStretch()
        return tab

    def _on_language_index(self, index):
        self._mark_pending()

    def _on_theme_index(self, index):
        self._mark_pending()

    def _on_runtime_index(self, index):
        self._mark_pending()

    def _save_update_preferences(self):
        self._mark_pending()

    def _save_display_preferences(self):
        self._mark_pending()

    def _save_quota_alert(self):
        self._mark_pending()

    def _save_shortcut(self, shortcut=None):
        shortcut = shortcut or self.shortcut_edit.sequence()
        if not parse_shortcut(shortcut):
            self.shortcut_status.setText(
                "Use a modifier plus a letter, number, or F-key."
                if self.translation_manager.get_language() == "en"
                else "请使用修饰键 + 字母、数字或 F 功能键。"
            )
            return
        self.shortcut_edit.set_sequence(shortcut)
        self.shortcut_status.setText(
            "Will apply after saving." if self.translation_manager.get_language() == "en" else "保存设置后才会注册并生效。"
        )
        self._mark_pending()

    def _save_window_preferences(self):
        self._mark_pending()

    def _mark_pending(self):
        self._settings_dirty = True
        self.save_btn.setEnabled(True)

    def _apply_settings(self):
        shortcut = self.shortcut_edit.sequence()
        english = self.translation_manager.get_language() == "en"
        if not parse_shortcut(shortcut):
            self.shortcut_status.setText(
                "Use a modifier plus a letter, number, or F-key." if english
                else "请使用修饰键 + 字母、数字或 F 功能键。"
            )
            return
        parent = self.parent()
        if shortcut != self.settings_manager.get_shortcut() and parent is not None and hasattr(parent, "try_register_shortcut"):
            if not parent.try_register_shortcut(shortcut):
                self.shortcut_edit.set_sequence(self.settings_manager.get_shortcut())
                self.shortcut_status.setText(
                    "Shortcut is occupied; choose another." if english else "快捷键被占用，请更换组合。"
                )
                return

        language = "zh" if self.lang_combo.currentIndex() == 0 else "en"
        theme = {0: "auto", 1: "light", 2: "dark"}.get(self.theme_combo.currentIndex(), "dark")
        timezone_mode = self.timezone_combo.currentData() or "system"
        timezone_identifier = self.timezone_edit.text().strip() or DEFAULT_FIXED_ZONE
        self.settings_manager.set_language(language)
        self.settings_manager.set_active_runtime(self.runtime_combo.currentData() or "codex")
        self.settings_manager.set_update_preferences(self.auto_update_cb.isChecked(), self.beta_cb.isChecked())
        self.settings_manager.set_shortcut(shortcut)
        self.settings_manager.set_window_preferences(
            self.always_on_top_cb.isChecked(), self.close_combo.currentData() or "tray",
        )
        self.settings_manager.set_desktop_status_enabled(self.desktop_status_cb.isChecked())
        self.settings_manager.set_desktop_status_style(self.desktop_style_combo.currentData() or "orb")
        self.settings_manager.set_desktop_status_size(self.desktop_size_combo.currentData() or "medium")
        self.settings_manager.set_desktop_status_scale(self.desktop_scale_spin.value() / 100)
        self.settings_manager.set_lightweight_mode(self.lightweight_mode_cb.isChecked())
        self.settings_manager.set_quota_display(self.quota_combo.currentData() or "remaining")
        self.settings_manager.set_reduce_motion(self.reduce_motion_cb.isChecked())
        self.settings_manager.set_quota_alert_threshold(self.quota_alert_combo.currentData() or 0)
        self.settings_manager.set_statistics_timezone(timezone_mode, timezone_identifier)
        configure_statistics_timezone(timezone_mode, timezone_identifier)
        self.settings_manager.set_theme(theme)
        self.translation_manager.set_language(language)
        self.theme_manager.set_theme(theme)
        self.theme_manager.apply_theme(QApplication.instance())
        self.settings_manager.save()
        self._settings_dirty = False
        self.accept()

    def reject(self):
        if self._settings_dirty:
            title = "放弃未保存的设置？" if self.translation_manager.get_language() == "zh" else "Discard unsaved settings?"
            text = (
                "这些更改尚未生效，确定放弃吗？"
                if self.translation_manager.get_language() == "zh"
                else "These changes have not been applied. Discard them?"
            )
            answer = QMessageBox.question(self, title, text, QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                return
        # 对话框会复用；取消时恢复为当前已保存配置，避免下次打开仍看到草稿。
        controls = (
            (self.lang_combo, 0 if self.settings_manager.get_language() == "zh" else 1),
            (self.runtime_combo, max(0, self.runtime_combo.findData(self.settings_manager.get_active_runtime()))),
            (self.theme_combo, {"auto": 0, "light": 1, "dark": 2}.get(self.settings_manager.get_theme(), 2)),
            (self.quota_combo, 0 if self.settings_manager.get_quota_display() == "remaining" else 1),
            (self.close_combo, max(0, self.close_combo.findData(self.settings_manager.get_window_preferences()[1]))),
            (self.quota_alert_combo, max(0, self.quota_alert_combo.findData(self.settings_manager.get_quota_alert_threshold()))),
        )
        for combo, index in controls:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        mode, identifier = self.settings_manager.get_statistics_timezone()
        self.timezone_combo.blockSignals(True)
        self.timezone_combo.setCurrentIndex({"system": 0, "utc": 1, "fixed": 2}.get(mode, 0))
        self.timezone_combo.blockSignals(False)
        self.timezone_edit.setText(identifier)
        self.timezone_edit.setEnabled(mode == "fixed")
        auto_update, include_beta = self.settings_manager.get_update_preferences()
        self.auto_update_cb.setChecked(auto_update)
        self.beta_cb.setChecked(include_beta)
        self.reduce_motion_cb.setChecked(self.settings_manager.get_reduce_motion())
        always_on_top, _ = self.settings_manager.get_window_preferences()
        self.always_on_top_cb.setChecked(always_on_top)
        desktop_enabled, _ = self.settings_manager.get_desktop_status_preferences()
        self.desktop_status_cb.setChecked(desktop_enabled)
        self.desktop_style_combo.blockSignals(True)
        self.desktop_style_combo.setCurrentIndex(max(0, self.desktop_style_combo.findData(self.settings_manager.get_desktop_status_style())))
        self.desktop_style_combo.blockSignals(False)
        self.desktop_size_combo.blockSignals(True)
        self.desktop_size_combo.setCurrentIndex(max(0, self.desktop_size_combo.findData(self.settings_manager.get_desktop_status_size())))
        self.desktop_size_combo.blockSignals(False)
        self.lightweight_mode_cb.setChecked(self.settings_manager.get_lightweight_mode())
        self.shortcut_edit.set_sequence(self.settings_manager.get_shortcut())
        self.shortcut_status.setText("")
        self._settings_dirty = False
        super().reject()

    def _refresh_diagnostics(self):
        symbols = {"ok": "●", "warning": "◆", "error": "×"}
        lines = [f"{symbols.get(item.level, '•')}  {item.name}：{item.detail}" for item in diagnose_data_sources()]
        parent = self.parent()
        if parent is not None and hasattr(parent, "hotkey_registered"):
            lines.append(
                ("●  全局快捷键：已注册" if parent.hotkey_registered else "◆  全局快捷键：注册失败或被占用")
            )
        self.diagnostic_label.setText("\n".join(lines))
        self._refresh_index_maintenance()

    def _refresh_index_maintenance(self):
        status = local_index_status()
        if status.available:
            self.index_status_label.setText(
                f"{status.file_count} 个文件、{status.event_count} 条派生事件；清理后仅会重建索引，不会删除原始日志。"
            )
        else:
            self.index_status_label.setText("尚未创建派生索引；不会影响 Codex 或 Claude Code 的原始日志。")

    def _clear_local_index(self):
        english = self.translation_manager.get_language() == "en"
        answer = QMessageBox.question(
            self,
            "Clear local index" if english else "清理本机索引",
            "Only derived analytics data will be removed. Raw logs stay untouched and the index rebuilds on next read. Continue?"
            if english else "仅删除派生统计索引，不会删除原始日志；下次读取会自动重建。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            clear_local_index()
            self._refresh_diagnostics()

    def _on_theme_changed(self):
        app = QApplication.instance()
        if app is not None:
            self.theme_manager.apply_theme(app)
        self._retranslate_ui()

    def _on_timezone_index(self, index):
        mode = self.timezone_combo.itemData(index) or "system"
        self.timezone_edit.setEnabled(mode == "fixed")
        self._mark_pending()

    def _on_timezone_text_changed(self):
        self._mark_pending()

    def _check_for_update(self):
        if self._update_thread is not None:
            return
        self.update_status_label.setText(
            "Checking GitHub Releases…" if self.translation_manager.get_language() == "en"
            else "正在检查 GitHub Release…"
        )
        self.check_update_btn.setEnabled(False)
        thread = QThread(self)
        worker = _UpdateWorker(APP_VERSION, self.beta_cb.isChecked())
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_update_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_update_worker)
        self._update_thread = thread
        self._update_worker = worker
        thread.start()

    def _on_update_finished(self, release):
        self.check_update_btn.setEnabled(True)
        self._latest_release = release
        self.download_update_btn.setEnabled(bool(release and release.download_url))
        if release is None:
            self.update_status_label.setText(
                "Up to date, or GitHub is temporarily unavailable."
                if self.translation_manager.get_language() == "en"
                else "已是最新版本，或暂时无法连接 GitHub。"
            )
        else:
            self.update_status_label.setText(
                f"New version {release.tag_name}\n{release.html_url}"
                if self.translation_manager.get_language() == "en"
                else f"发现新版本 {release.tag_name}\n{release.html_url}"
            )

    def _open_release(self):
        url = self._latest_release.html_url if self._latest_release and self._latest_release.html_url else f"https://github.com/{APP_REPO}/releases"
        QDesktopServices.openUrl(QUrl(url))

    def _download_update(self):
        if self._latest_release and self._latest_release.download_url:
            QDesktopServices.openUrl(QUrl(self._latest_release.download_url))

    def _clear_update_worker(self):
        self._update_thread = None
        self._update_worker = None

    def _on_settings_changed(self):
        self._retranslate_ui()
        self._refresh_diagnostics()

    def _retranslate_ui(self):
        tr = self.translation_manager.tr
        english = self.translation_manager.get_language() == "en"
        self.setWindowTitle(f"CodexUU {tr('settings')}")
        self.heading_title.setText(tr("settings"))
        self.tabs.setTabText(0, tr("general"))
        self.tabs.setTabText(1, tr("display"))
        self.tabs.setTabText(2, tr("system"))
        self.cancel_btn.setText("Cancel" if english else "取消")
        self.save_btn.setText("Save settings" if english else "保存设置")
        self.preference_card.setTitle("Preferences" if english else "偏好")
        self.window_card.setTitle("Window & shortcut" if english else "窗口与快捷键")
        self.appearance_card.setTitle("Appearance" if english else "外观")
        self.update_card.setTitle("Updates" if english else "更新")
        self.timezone_card.setTitle("Statistics" if english else "统计口径")
        self.diagnostic_card.setTitle("Data source diagnostics" if english else "数据源诊断")
        self.alert_card.setTitle("Quota alerts" if english else "额度提醒")
        self.maintenance_card.setTitle("Data maintenance" if english else "数据维护")
        self.preference_form.labelForField(self.lang_combo).setText("Language" if english else "语言")
        self.preference_form.labelForField(self.runtime_combo).setText("Data source" if english else "数据源")
        self.auto_update_cb.setText("Auto-check GitHub Release updates" if english else "自动检查 GitHub Release 更新")
        self.beta_cb.setText("Receive Beta / prerelease versions" if english else "接收 Beta / prerelease 版本")
        self.appearance_form.labelForField(self.theme_combo).setText("Theme" if english else "主题")
        self.appearance_form.labelForField(self.quota_combo).setText("Quota display" if english else "额度口径")
        self.reduce_motion_cb.setText("Reduce motion" if english else "减少动态效果")
        self.window_form.labelForField(self.shortcut_row).setText("Global shortcut" if english else "全局快捷键")
        self.shortcut_reset.setText("Reset" if english else "恢复默认")
        self.window_form.labelForField(self.shortcut_status).setText("Status" if english else "状态")
        self.always_on_top_cb.setText("Keep main window on top" if english else "主窗口始终置顶")
        self.desktop_status_cb.setText("Show desktop status panel" if english else "在桌面显示状态悬浮窗")
        self.window_form.labelForField(self.desktop_style_combo).setText("Desktop panel style" if english else "桌面悬浮样式")
        self.window_form.labelForField(self.desktop_size_combo).setText("Desktop panel size" if english else "悬浮窗大小")
        self.lightweight_mode_cb.setText("Lightweight mode (hide taskbar icon)" if english else "轻量模式（运行时不显示任务栏图标）")
        self.window_form.labelForField(self.close_combo).setText("Close main window" if english else "关闭主窗口")
        self.appearance_form.labelForField(self.display_note).setText("About" if english else "说明")
        self.display_note.setText(
            "The interface automatically adjusts surfaces, text, and controls for the selected theme."
            if english else "界面会根据主题自动调整背景、卡片、文字和控件对比度。"
        )
        self.update_form.labelForField(self.check_update_btn).setText("Manual check" if english else "手动检查")
        self.update_form.labelForField(self.update_status_label).setText("Status" if english else "状态")
        version_field = self.update_form.itemAt(0, QFormLayout.ItemRole.FieldRole)
        if version_field and version_field.widget():
            label = self.update_form.labelForField(version_field.widget())
            if label:
                label.setText("Current version" if english else "当前版本")
        self.check_update_btn.setText("Check for updates" if english else "检查更新")
        self.download_update_btn.setText("Download update" if english else "下载更新")
        self.open_release_btn.setText("Open release" if english else "打开 Release")
        self.diagnostic_button.setText("Check again" if english else "重新检测")
        self.alert_form.labelForField(self.quota_alert_combo).setText("Alert threshold" if english else "提醒阈值")
        self.alert_form.labelForField(self.alert_note).setText("About" if english else "说明")
        self.alert_note.setText(
            "Each quota window notifies once per reset cycle after remaining quota falls below this threshold."
            if english else "额度低于阈值时，每个额度窗口在本次重置周期内只通知一次。"
        )
        self.maintenance_form.labelForField(self.index_status_label).setText("Local index" if english else "本机索引")
        self.maintenance_form.labelForField(self.clear_index_btn).setText("Rebuildable data" if english else "可重建数据")
        self.clear_index_btn.setText("Clear and rebuild on next read" if english else "清理并在下次读取时重建")
        self.diagnostic_form.labelForField(self.data_scope_label).setText("Scope" if english else "统计范围")
        self.data_scope_label.setText(
            "Usage, trends, and projects are local records only. The local index stores derived metrics, not transcript text."
            if english else "所有用量、趋势和项目数字均来自本机记录；本机索引只保存派生统计，不保存对话正文。"
        )
        self.timezone_form.labelForField(self.timezone_combo).setText("Calendar day" if english else "自然日")
        self.timezone_form.labelForField(self.timezone_edit).setText("IANA zone" if english else "IANA 标识")
        for combo, labels in (
            (self.theme_combo, (("Automatic", "Light", "Dark") if english else ("自动", "浅色", "深色"))),
            (self.timezone_combo, (("Follow system", "UTC", "Fixed IANA zone") if english else ("跟随系统", "UTC", "固定 IANA 时区"))),
            (self.quota_combo, (("Show remaining", "Show used") if english else ("显示剩余", "显示已用"))),
            (self.close_combo, (("Hide to tray", "Minimize", "Quit application") if english else ("隐藏到托盘", "最小化", "退出程序"))),
            (self.desktop_style_combo, (
                ("Info dial A", "Dual-ring gauge A", "Minimal ring B", "Status capsule B", "Dual-track card B")
                if english else ("信息圆盘 A", "双环仪表 A", "极简圆环 B", "状态胶囊 B", "双轨卡片 B")
            )),
            (self.desktop_size_combo, (("Small", "Medium", "Large") if english else ("小", "中", "大"))),
        ):
            for index, label in enumerate(labels):
                combo.setItemText(index, label)
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(0 if self.translation_manager.get_language() == "zh" else 1)
        self.lang_combo.blockSignals(False)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex({"auto": 0, "light": 1, "dark": 2}.get(self.theme_manager.theme, 2))
        self.theme_combo.blockSignals(False)
