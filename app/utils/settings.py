from __future__ import annotations
import json
from pathlib import Path
from typing import Callable

DEFAULT_LANGUAGE = "zh"
DEFAULT_THEME = "dark"

class SettingsManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.language = DEFAULT_LANGUAGE
        self.theme = DEFAULT_THEME
        self.listeners: list[Callable] = []
    
    def get_language(self) -> str:
        return self.language
    
    def get_theme(self) -> str:
        return self.theme
    
    def set_language(self, lang: str):
        if lang in ("zh", "en"):
            self.language = lang
            self._notify_listeners()
    
    def set_theme(self, theme: str):
        if theme in ("auto", "light", "dark"):
            self.theme = theme
            self._notify_listeners()
    
    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.language = data.get("language", DEFAULT_LANGUAGE)
                self.theme = data.get("theme", DEFAULT_THEME)
            except (json.JSONDecodeError, KeyError):
                self.language = DEFAULT_LANGUAGE
                self.theme = DEFAULT_THEME
    
    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "language": self.language,
            "theme": self.theme
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_listener(self, callback: Callable):
        self.listeners.append(callback)
    
    def _notify_listeners(self):
        for listener in self.listeners:
            listener()