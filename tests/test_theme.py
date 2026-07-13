import pytest
from app.utils.theme import ThemeManager

def test_theme_manager_default_theme():
    manager = ThemeManager()
    assert manager.get_theme() == "dark"

def test_theme_manager_set_theme():
    manager = ThemeManager()
    manager.set_theme("light")
    assert manager.get_theme() == "light"
    manager.set_theme("dark")
    assert manager.get_theme() == "dark"

def test_theme_manager_get_stylesheet():
    manager = ThemeManager()
    manager.set_theme("dark")
    style = manager.get_stylesheet()
    assert "#1e1e3a" in style or "#12122a" in style
    
    manager.set_theme("light")
    style = manager.get_stylesheet()
    assert "#ffffff" in style or "#f5f5f5" in style