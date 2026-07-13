from __future__ import annotations
import sys
from typing import Callable

DARK_THEME = """
QMainWindow { background: #12122a; }
QDialog { background: #1e1e3a; color: #e0e0e0; }
QLabel { color: #ccc; }
QPushButton { color: #e0e0e0; }
QGroupBox { color: #fff; border: 1px solid #333; }
QTabWidget::pane { background: rgba(255,255,255,0.03); border: 1px solid #333; }
QTabBar::tab { background: rgba(255,255,255,0.06); color: #888; }
QTabBar::tab:selected { background: rgba(96,165,250,0.3); color: #fff; }
QComboBox { background: rgba(255,255,255,0.08); color: #e0e0e0; border: 1px solid #444; }
QCheckBox { color: #bbb; }
"""

LIGHT_THEME = """
QMainWindow { background: #f5f5f5; }
QDialog { background: #ffffff; color: #333333; }
QLabel { color: #555555; }
QPushButton { color: #333333; }
QGroupBox { color: #333333; border: 1px solid #dddddd; }
QTabWidget::pane { background: #ffffff; border: 1px solid #dddddd; }
QTabBar::tab { background: #eeeeee; color: #666666; }
QTabBar::tab:selected { background: #ffffff; color: #333333; }
QComboBox { background: #ffffff; color: #333333; border: 1px solid #cccccc; }
QCheckBox { color: #555555; }
"""

class ThemeManager:
    def __init__(self):
        self.theme = "dark"
        self.listeners: list[Callable] = []
    
    def get_theme(self) -> str:
        return self.theme
    
    def set_theme(self, theme: str):
        if theme in ("auto", "light", "dark"):
            if theme == "auto":
                self.theme = self._detect_system_theme()
            else:
                self.theme = theme
            self._notify_listeners()
    
    def get_stylesheet(self) -> str:
        if self.theme == "dark":
            return DARK_THEME
        else:
            return LIGHT_THEME
    
    def apply_theme(self, app):
        app.setStyleSheet(self.get_stylesheet())
    
    def _detect_system_theme(self) -> str:
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                winreg.CloseKey(key)
                return "light" if value == 1 else "dark"
            except Exception:
                return "dark"
        return "dark"
    
    def add_listener(self, callback: Callable):
        self.listeners.append(callback)
    
    def _notify_listeners(self):
        for listener in self.listeners:
            listener()