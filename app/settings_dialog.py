from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget, QApplication,
    QKeySequenceEdit,
)

from app.constants import APP_REPO, APP_VERSION
from app.utils.data_diagnostics import diagnose_data_sources
from app.utils.global_hotkey import parse_shortcut
from app.utils.settings import SettingsManager
from app.utils.statistics_timezone import DEFAULT_FIXED_ZONE, configure_statistics_timezone
from app.utils.theme import ThemeManager
from app.utils.translation import TranslationManager
from app.utils.update_checker import check_for_update


def _combo(items):
    combo = QComboBox()
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

        self.setObjectName("settingsDialog")
        self.setWindowTitle("CodexUU 设置")
        self.setMinimumSize(620, 560)
        self.resize(660, 640)
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
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("primaryButton")
        self.close_btn.setMinimumWidth(96)
        self.close_btn.clicked.connect(self.accept)
        footer.addWidget(self.close_btn)
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
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 14, 8, 8)
        self.preference_card, form = self._card("偏好")
        card = self.preference_card
        self.preference_form = form
        self.lang_combo = _combo(["中文", "English"])
        self.lang_combo.setCurrentIndex(0 if self.translation_manager.get_language() == "zh" else 1)
        self.lang_combo.currentIndexChanged.connect(self._on_language_index)
        form.addRow("语言", self.lang_combo)
        self.runtime_combo = QComboBox()
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
        self.shortcut_edit = QKeySequenceEdit(QKeySequence(self.settings_manager.get_shortcut()))
        self.shortcut_edit.editingFinished.connect(self._save_shortcut)
        window_form.addRow("全局快捷键", self.shortcut_edit)
        self.shortcut_status = QLabel("")
        self.shortcut_status.setObjectName("caption")
        window_form.addRow("状态", self.shortcut_status)
        always_on_top, close_behavior = self.settings_manager.get_window_preferences()
        self.always_on_top_cb = _check("主窗口始终置顶", always_on_top)
        self.always_on_top_cb.stateChanged.connect(self._save_window_preferences)
        window_form.addRow(self.always_on_top_cb)
        self.close_combo = QComboBox()
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
        self.quota_combo = QComboBox()
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
        layout = QVBoxLayout(tab)
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
        self.timezone_combo = QComboBox()
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
        self.diagnostic_button = QPushButton("重新检测")
        self.diagnostic_button.setObjectName("iconButton")
        self.diagnostic_button.clicked.connect(self._refresh_diagnostics)
        diagnostic_form.addRow(self.diagnostic_button)
        layout.addWidget(self.diagnostic_card)
        self._refresh_diagnostics()
        layout.addStretch()
        return tab

    def _on_language_index(self, index):
        language = "zh" if index == 0 else "en"
        self.translation_manager.set_language(language)
        self.settings_manager.set_language(language)
        self.settings_manager.save()

    def _on_theme_index(self, index):
        theme = {0: "auto", 1: "light", 2: "dark"}.get(index, "dark")
        self.theme_manager.set_theme(theme)
        self.settings_manager.set_theme(theme)
        self.settings_manager.save()

    def _on_runtime_index(self, index):
        runtime = self.runtime_combo.itemData(index) or "codex"
        self.settings_manager.set_active_runtime(runtime)
        self.settings_manager.save()

    def _save_update_preferences(self):
        self.settings_manager.set_update_preferences(self.auto_update_cb.isChecked(), self.beta_cb.isChecked())
        self.settings_manager.save()

    def _save_display_preferences(self):
        self.settings_manager.set_quota_display(self.quota_combo.currentData() or "remaining")
        self.settings_manager.set_reduce_motion(self.reduce_motion_cb.isChecked())
        self.settings_manager.save()

    def _save_shortcut(self):
        shortcut = self.shortcut_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if not parse_shortcut(shortcut):
            self.shortcut_status.setText(
                "Use a modifier plus a letter, number, or F-key."
                if self.translation_manager.get_language() == "en"
                else "请使用修饰键 + 字母、数字或 F 功能键。"
            )
            return
        self.settings_manager.set_shortcut(shortcut)
        self.settings_manager.save()
        parent = self.parent()
        registered = bool(parent is not None and getattr(parent, "hotkey_registered", False))
        self.shortcut_status.setText(
            ("Saved; active globally." if self.translation_manager.get_language() == "en" else "已保存并全局生效。")
            if registered else
            ("Shortcut is occupied; choose another." if self.translation_manager.get_language() == "en" else "快捷键被占用，请更换组合。")
        )

    def _save_window_preferences(self):
        self.settings_manager.set_window_preferences(
            self.always_on_top_cb.isChecked(), self.close_combo.currentData() or "tray",
        )
        self.settings_manager.save()

    def _refresh_diagnostics(self):
        symbols = {"ok": "●", "warning": "◆", "error": "×"}
        lines = [f"{symbols.get(item.level, '•')}  {item.name}：{item.detail}" for item in diagnose_data_sources()]
        parent = self.parent()
        if parent is not None and hasattr(parent, "hotkey_registered"):
            lines.append(
                ("●  全局快捷键：已注册" if parent.hotkey_registered else "◆  全局快捷键：注册失败或被占用")
            )
        self.diagnostic_label.setText("\n".join(lines))

    def _on_theme_changed(self):
        app = QApplication.instance()
        if app is not None:
            self.theme_manager.apply_theme(app)
        self._retranslate_ui()

    def _on_timezone_index(self, index):
        mode = self.timezone_combo.itemData(index) or "system"
        identifier = self.timezone_edit.text().strip() or DEFAULT_FIXED_ZONE
        self.timezone_edit.setEnabled(mode == "fixed")
        self.settings_manager.set_statistics_timezone(mode, identifier)
        configure_statistics_timezone(mode, identifier)
        self.settings_manager.save()

    def _on_timezone_text_changed(self):
        if self.timezone_combo.currentData() != "fixed":
            return
        identifier = self.timezone_edit.text().strip() or DEFAULT_FIXED_ZONE
        self.settings_manager.set_statistics_timezone("fixed", identifier)
        configure_statistics_timezone("fixed", identifier)
        self.settings_manager.save()

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
        self.close_btn.setText(tr("close"))
        self.preference_card.setTitle("Preferences" if english else "偏好")
        self.window_card.setTitle("Window & shortcut" if english else "窗口与快捷键")
        self.appearance_card.setTitle("Appearance" if english else "外观")
        self.update_card.setTitle("Updates" if english else "更新")
        self.timezone_card.setTitle("Statistics" if english else "统计口径")
        self.diagnostic_card.setTitle("Data source diagnostics" if english else "数据源诊断")
        self.preference_form.labelForField(self.lang_combo).setText("Language" if english else "语言")
        self.preference_form.labelForField(self.runtime_combo).setText("Data source" if english else "数据源")
        self.auto_update_cb.setText("Auto-check GitHub Release updates" if english else "自动检查 GitHub Release 更新")
        self.beta_cb.setText("Receive Beta / prerelease versions" if english else "接收 Beta / prerelease 版本")
        self.appearance_form.labelForField(self.theme_combo).setText("Theme" if english else "主题")
        self.appearance_form.labelForField(self.quota_combo).setText("Quota display" if english else "额度口径")
        self.reduce_motion_cb.setText("Reduce motion" if english else "减少动态效果")
        self.window_form.labelForField(self.shortcut_edit).setText("Global shortcut" if english else "全局快捷键")
        self.window_form.labelForField(self.shortcut_status).setText("Status" if english else "状态")
        self.always_on_top_cb.setText("Keep main window on top" if english else "主窗口始终置顶")
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
        self.timezone_form.labelForField(self.timezone_combo).setText("Calendar day" if english else "自然日")
        self.timezone_form.labelForField(self.timezone_edit).setText("IANA zone" if english else "IANA 标识")
        for combo, labels in (
            (self.theme_combo, (("Automatic", "Light", "Dark") if english else ("自动", "浅色", "深色"))),
            (self.timezone_combo, (("Follow system", "UTC", "Fixed IANA zone") if english else ("跟随系统", "UTC", "固定 IANA 时区"))),
            (self.quota_combo, (("Show remaining", "Show used") if english else ("显示剩余", "显示已用"))),
            (self.close_combo, (("Hide to tray", "Minimize", "Quit application") if english else ("隐藏到托盘", "最小化", "退出程序"))),
        ):
            for index, label in enumerate(labels):
                combo.setItemText(index, label)
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(0 if self.translation_manager.get_language() == "zh" else 1)
        self.lang_combo.blockSignals(False)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex({"auto": 0, "light": 1, "dark": 2}.get(self.theme_manager.theme, 2))
        self.theme_combo.blockSignals(False)
