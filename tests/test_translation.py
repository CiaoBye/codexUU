import pytest
from app.utils.translation import TranslationManager

def test_translation_manager_default_language():
    manager = TranslationManager()
    assert manager.get_language() == "zh"

def test_translation_manager_chinese():
    manager = TranslationManager()
    manager.set_language("zh")
    assert manager.tr("settings") == "设置"
    assert manager.tr("language") == "语言"
    assert manager.tr("theme") == "外观"

def test_translation_manager_english():
    manager = TranslationManager()
    manager.set_language("en")
    assert manager.tr("settings") == "Settings"
    assert manager.tr("language") == "Language"
    assert manager.tr("theme") == "Appearance"

def test_translation_manager_fallback():
    manager = TranslationManager()
    assert manager.tr("nonexistent_key") == "nonexistent_key"