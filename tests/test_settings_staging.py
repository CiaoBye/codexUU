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
    assert manager.get_quota_alert_threshold() == 20
    assert manager.get_desktop_status_preferences()[0] is True
    assert manager.get_desktop_status_style() == "orb"

    dialog._apply_settings()
    assert manager.get_quota_alert_threshold() == 30
    assert manager.get_desktop_status_preferences()[0] is False
    assert manager.get_desktop_status_style() == "mini"
    assert app is not None
