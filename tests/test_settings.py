import pytest
import json
import tempfile
from pathlib import Path
from app.utils.settings import SettingsManager

def test_settings_manager_default_values():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = SettingsManager(config_path)
        assert manager.get_language() == "zh"
        assert manager.get_theme() == "dark"
        assert manager.get_active_runtime() == "codex"
        assert manager.get_quota_display() == "remaining"
        assert manager.get_model_scope() == "all"
        assert manager.get_shortcut() == "Ctrl+U"
        assert manager.get_reduce_motion() is False
        assert manager.get_window_preferences() == (False, "tray")
        assert manager.get_quota_alert_threshold() == 20
        assert manager.get_desktop_status_preferences() == (True, None)
        assert manager.get_desktop_status_style() == "orb"
        assert manager.get_desktop_status_size() == "medium"
        assert manager.get_desktop_status_scale() == 1.0
        assert manager.get_lightweight_mode() is True

def test_settings_manager_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = SettingsManager(config_path)
        manager.set_language("en")
        manager.set_theme("light")
        manager.set_statistics_timezone("fixed", "Asia/Shanghai")
        manager.set_active_runtime("claudeCode")
        manager.set_quota_display("used")
        manager.set_model_scope("gpt")
        manager.set_shortcut("Ctrl+Alt+K")
        manager.set_reduce_motion(True)
        manager.set_window_preferences(True, "minimize")
        manager.set_quota_alert_threshold(30)
        manager.set_desktop_status_enabled(True)
        manager.set_desktop_status_position(120, 240)
        manager.set_desktop_status_style("tracks")
        manager.set_desktop_status_size("large")
        manager.set_desktop_status_scale(0.63)
        manager.set_lightweight_mode(False)
        manager.save()
        
        manager2 = SettingsManager(config_path)
        manager2.load()
        assert manager2.get_language() == "en"
        assert manager2.get_theme() == "light"
        assert manager2.get_statistics_timezone() == ("fixed", "Asia/Shanghai")
        assert manager2.get_active_runtime() == "claudeCode"
        assert manager2.get_quota_display() == "used"
        assert manager2.get_model_scope() == "gpt"
        assert manager2.get_shortcut() == "Ctrl+Alt+K"
        assert manager2.get_reduce_motion() is True
        assert manager2.get_window_preferences() == (True, "minimize")
        assert manager2.get_quota_alert_threshold() == 30
        assert manager2.get_desktop_status_preferences() == (True, (120, 240))
        assert manager2.get_desktop_status_style() == "tracks"
        assert manager2.get_desktop_status_size() == "large"
        assert manager2.get_desktop_status_scale() == 0.63
        assert manager2.get_lightweight_mode() is False

def test_settings_manager_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "nonexistent.json"
        manager = SettingsManager(config_path)
        assert manager.get_language() == "zh"
        assert manager.get_theme() == "dark"
