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

def test_settings_manager_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = SettingsManager(config_path)
        manager.set_language("en")
        manager.set_theme("light")
        manager.save()
        
        manager2 = SettingsManager(config_path)
        manager2.load()
        assert manager2.get_language() == "en"
        assert manager2.get_theme() == "light"

def test_settings_manager_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "nonexistent.json"
        manager = SettingsManager(config_path)
        assert manager.get_language() == "zh"
        assert manager.get_theme() == "dark"