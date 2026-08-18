import pytest
import tempfile
from pathlib import Path
from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager

def test_settings_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Create managers
        settings = SettingsManager(config_path)
        translation = TranslationManager()
        theme = ThemeManager()
        
        # Initial state
        assert settings.get_language() == "zh"
        assert translation.get_language() == "zh"
        assert theme.get_theme() == "dark"
        
        # Change language
        settings.set_language("en")
        translation.set_language(settings.get_language())
        assert translation.tr("settings") == "Settings"
        
        # Change theme
        settings.set_theme("light")
        theme.set_theme(settings.get_theme())
        assert theme.get_theme() == "light"
        
        # Save and reload
        settings.save()
        settings2 = SettingsManager(config_path)
        settings2.load()
        assert settings2.get_language() == "en"
        assert settings2.get_theme() == "light"