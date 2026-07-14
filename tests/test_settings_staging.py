import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.settings_dialog import SettingsDialog
from app.utils.settings import SettingsManager
from app.utils.theme import ThemeManager
from app.utils.translation import TranslationManager


def test_setting_controls_apply_only_after_save(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(Path(tmp_path) / "config.json")
    dialog = SettingsDialog(
        settings_manager=manager,
        translation_manager=TranslationManager(),
        theme_manager=ThemeManager(),
    )

    dialog.quota_alert_combo.setCurrentIndex(dialog.quota_alert_combo.findData(30))
    dialog.desktop_status_cb.setChecked(False)
    dialog.desktop_style_combo.setCurrentIndex(dialog.desktop_style_combo.findData("mini"))
    dialog.desktop_size_combo.setCurrentIndex(dialog.desktop_size_combo.findData("large"))
    assert manager.get_quota_alert_threshold() == 20
    assert manager.get_desktop_status_preferences()[0] is True
    assert manager.get_desktop_status_style() == "orb"
    assert manager.get_desktop_status_size() == "medium"

    dialog._apply_settings()
    assert manager.get_quota_alert_threshold() == 30
    assert manager.get_desktop_status_preferences()[0] is False
    assert manager.get_desktop_status_style() == "mini"
    assert manager.get_desktop_status_size() == "large"
    assert app is not None


def test_desktop_status_style_names_match_finalized_designs(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(
        settings_manager=SettingsManager(Path(tmp_path) / "config.json"),
        translation_manager=TranslationManager(),
        theme_manager=ThemeManager(),
    )
    assert [dialog.desktop_style_combo.itemText(index) for index in range(dialog.desktop_style_combo.count())] == [
        "信息圆盘 A",
        "双环仪表 A",
        "极简圆环 B",
        "状态胶囊 B",
        "双轨卡片 B",
    ]
    dialog.close()
    assert app is not None
