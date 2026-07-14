from __future__ import annotations
import json
from pathlib import Path
from typing import Callable

DEFAULT_LANGUAGE = "zh"
DEFAULT_THEME = "dark"
DEFAULT_STATISTICS_TIMEZONE = "system"
DEFAULT_STATISTICS_TIMEZONE_ID = "Asia/Shanghai"
DEFAULT_AUTO_UPDATE = True
DEFAULT_INCLUDE_BETA = True
DEFAULT_ACTIVE_RUNTIME = "codex"
DEFAULT_QUOTA_DISPLAY = "remaining"
DEFAULT_MODEL_SCOPE = "all"
DEFAULT_SHORTCUT = "Ctrl+U"
DEFAULT_REDUCE_MOTION = False
DEFAULT_ALWAYS_ON_TOP = False
DEFAULT_CLOSE_BEHAVIOR = "tray"
DEFAULT_QUOTA_ALERT_THRESHOLD = 20
DEFAULT_DESKTOP_STATUS_ENABLED = True
DEFAULT_DESKTOP_STATUS_STYLE = "orb"
DEFAULT_DESKTOP_STATUS_SIZE = "medium"
DEFAULT_LIGHTWEIGHT_MODE = True
DESKTOP_STATUS_STYLES = ("orb", "halo", "mini", "capsule", "tracks")

class SettingsManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.language = DEFAULT_LANGUAGE
        self.theme = DEFAULT_THEME
        self.statistics_timezone = DEFAULT_STATISTICS_TIMEZONE
        self.statistics_timezone_id = DEFAULT_STATISTICS_TIMEZONE_ID
        self.auto_update = DEFAULT_AUTO_UPDATE
        self.include_beta = DEFAULT_INCLUDE_BETA
        self.active_runtime = DEFAULT_ACTIVE_RUNTIME
        self.quota_display = DEFAULT_QUOTA_DISPLAY
        self.model_scope = DEFAULT_MODEL_SCOPE
        self.shortcut = DEFAULT_SHORTCUT
        self.reduce_motion = DEFAULT_REDUCE_MOTION
        self.always_on_top = DEFAULT_ALWAYS_ON_TOP
        self.close_behavior = DEFAULT_CLOSE_BEHAVIOR
        self.quota_alert_threshold = DEFAULT_QUOTA_ALERT_THRESHOLD
        self.desktop_status_enabled = DEFAULT_DESKTOP_STATUS_ENABLED
        self.desktop_status_position: tuple[int, int] | None = None
        self.desktop_status_style = DEFAULT_DESKTOP_STATUS_STYLE
        self.desktop_status_size = DEFAULT_DESKTOP_STATUS_SIZE
        self.lightweight_mode = DEFAULT_LIGHTWEIGHT_MODE
        self.listeners: list[Callable] = []
    
    def get_language(self) -> str:
        return self.language
    
    def get_theme(self) -> str:
        return self.theme

    def get_statistics_timezone(self) -> tuple[str, str]:
        return self.statistics_timezone, self.statistics_timezone_id

    def get_update_preferences(self) -> tuple[bool, bool]:
        return self.auto_update, self.include_beta

    def get_active_runtime(self) -> str:
        return self.active_runtime

    def get_quota_display(self) -> str:
        return self.quota_display

    def get_model_scope(self) -> str:
        return self.model_scope

    def get_shortcut(self) -> str:
        return self.shortcut

    def get_reduce_motion(self) -> bool:
        return self.reduce_motion

    def get_window_preferences(self) -> tuple[bool, str]:
        return self.always_on_top, self.close_behavior

    def get_quota_alert_threshold(self) -> int:
        return self.quota_alert_threshold

    def get_desktop_status_preferences(self) -> tuple[bool, tuple[int, int] | None]:
        return self.desktop_status_enabled, self.desktop_status_position

    def get_lightweight_mode(self) -> bool:
        return self.lightweight_mode

    def get_desktop_status_style(self) -> str:
        return self.desktop_status_style

    def get_desktop_status_size(self) -> str:
        return self.desktop_status_size

    def set_active_runtime(self, runtime: str):
        if runtime in ("codex", "claudeCode"):
            self.active_runtime = runtime
            self._notify_listeners()

    def set_quota_display(self, mode: str):
        if mode in ("remaining", "used"):
            self.quota_display = mode
            self._notify_listeners()

    def set_model_scope(self, scope: str):
        if scope in ("gpt", "all"):
            self.model_scope = scope
            self._notify_listeners()

    def set_shortcut(self, shortcut: str):
        value = str(shortcut or "").strip()
        if value:
            self.shortcut = value
            self._notify_listeners()

    def set_reduce_motion(self, enabled: bool):
        self.reduce_motion = bool(enabled)
        self._notify_listeners()

    def set_window_preferences(self, always_on_top: bool, close_behavior: str):
        self.always_on_top = bool(always_on_top)
        self.close_behavior = close_behavior if close_behavior in ("tray", "minimize", "quit") else DEFAULT_CLOSE_BEHAVIOR
        self._notify_listeners()

    def set_quota_alert_threshold(self, threshold: int):
        try:
            value = int(threshold)
        except (TypeError, ValueError):
            value = DEFAULT_QUOTA_ALERT_THRESHOLD
        self.quota_alert_threshold = value if value in (0, 10, 20, 30, 50) else DEFAULT_QUOTA_ALERT_THRESHOLD
        self._notify_listeners()

    def set_desktop_status_enabled(self, enabled: bool):
        self.desktop_status_enabled = bool(enabled)
        self._notify_listeners()

    def set_desktop_status_position(self, x: int, y: int):
        self.desktop_status_position = (int(x), int(y))
        self._notify_listeners()

    def set_desktop_status_style(self, style: str):
        if style in DESKTOP_STATUS_STYLES:
            self.desktop_status_style = style
            self._notify_listeners()

    def set_desktop_status_size(self, size: str):
        if size in ("small", "medium", "large"):
            self.desktop_status_size = size
            self._notify_listeners()

    def set_lightweight_mode(self, enabled: bool):
        self.lightweight_mode = bool(enabled)
        self._notify_listeners()

    def set_update_preferences(self, auto_update: bool, include_beta: bool):
        self.auto_update = bool(auto_update)
        self.include_beta = bool(include_beta)
        self._notify_listeners()

    def set_statistics_timezone(self, mode: str, identifier: str = DEFAULT_STATISTICS_TIMEZONE_ID):
        if mode in ("system", "utc", "fixed"):
            self.statistics_timezone = mode
            self.statistics_timezone_id = identifier or DEFAULT_STATISTICS_TIMEZONE_ID
            self._notify_listeners()
    
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
                language = data.get("language", DEFAULT_LANGUAGE)
                theme = data.get("theme", DEFAULT_THEME)
                timezone_mode = data.get("statistics_timezone", DEFAULT_STATISTICS_TIMEZONE)
                timezone_id = data.get("statistics_timezone_id", DEFAULT_STATISTICS_TIMEZONE_ID)
                auto_update = data.get("auto_update", DEFAULT_AUTO_UPDATE)
                include_beta = data.get("include_beta", DEFAULT_INCLUDE_BETA)
                active_runtime = data.get("active_runtime", DEFAULT_ACTIVE_RUNTIME)
                quota_display = data.get("quota_display", DEFAULT_QUOTA_DISPLAY)
                model_scope = data.get("model_scope", DEFAULT_MODEL_SCOPE)
                shortcut = data.get("shortcut", DEFAULT_SHORTCUT)
                reduce_motion = data.get("reduce_motion", DEFAULT_REDUCE_MOTION)
                always_on_top = data.get("always_on_top", DEFAULT_ALWAYS_ON_TOP)
                close_behavior = data.get("close_behavior", DEFAULT_CLOSE_BEHAVIOR)
                quota_alert_threshold = data.get("quota_alert_threshold", DEFAULT_QUOTA_ALERT_THRESHOLD)
                desktop_status_enabled = data.get("desktop_status_enabled", DEFAULT_DESKTOP_STATUS_ENABLED)
                desktop_status_position = data.get("desktop_status_position")
                desktop_status_style = data.get("desktop_status_style", DEFAULT_DESKTOP_STATUS_STYLE)
                desktop_status_size = data.get("desktop_status_size", DEFAULT_DESKTOP_STATUS_SIZE)
                lightweight_mode = data.get("lightweight_mode", DEFAULT_LIGHTWEIGHT_MODE)
                self.language = language if language in ("zh", "en") else DEFAULT_LANGUAGE
                self.theme = theme if theme in ("auto", "light", "dark") else DEFAULT_THEME
                self.statistics_timezone = timezone_mode if timezone_mode in ("system", "utc", "fixed") else DEFAULT_STATISTICS_TIMEZONE
                self.statistics_timezone_id = str(timezone_id or DEFAULT_STATISTICS_TIMEZONE_ID)
                self.auto_update = bool(auto_update)
                self.include_beta = bool(include_beta)
                self.active_runtime = active_runtime if active_runtime in ("codex", "claudeCode") else DEFAULT_ACTIVE_RUNTIME
                self.quota_display = quota_display if quota_display in ("remaining", "used") else DEFAULT_QUOTA_DISPLAY
                self.model_scope = model_scope if model_scope in ("gpt", "all") else DEFAULT_MODEL_SCOPE
                self.shortcut = str(shortcut or DEFAULT_SHORTCUT)
                self.reduce_motion = bool(reduce_motion)
                self.always_on_top = bool(always_on_top)
                self.close_behavior = close_behavior if close_behavior in ("tray", "minimize", "quit") else DEFAULT_CLOSE_BEHAVIOR
                self.set_quota_alert_threshold(quota_alert_threshold)
                self.desktop_status_enabled = bool(desktop_status_enabled)
                self.desktop_status_position = (
                    (int(desktop_status_position[0]), int(desktop_status_position[1]))
                    if isinstance(desktop_status_position, list) and len(desktop_status_position) == 2
                    else None
                )
                self.desktop_status_style = desktop_status_style if desktop_status_style in DESKTOP_STATUS_STYLES else DEFAULT_DESKTOP_STATUS_STYLE
                self.desktop_status_size = desktop_status_size if desktop_status_size in ("small", "medium", "large") else DEFAULT_DESKTOP_STATUS_SIZE
                self.lightweight_mode = bool(lightweight_mode)
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                self.language = DEFAULT_LANGUAGE
                self.theme = DEFAULT_THEME
                self.statistics_timezone = DEFAULT_STATISTICS_TIMEZONE
                self.statistics_timezone_id = DEFAULT_STATISTICS_TIMEZONE_ID
                self.auto_update = DEFAULT_AUTO_UPDATE
                self.include_beta = DEFAULT_INCLUDE_BETA
                self.active_runtime = DEFAULT_ACTIVE_RUNTIME
                self.quota_display = DEFAULT_QUOTA_DISPLAY
                self.model_scope = DEFAULT_MODEL_SCOPE
                self.shortcut = DEFAULT_SHORTCUT
                self.reduce_motion = DEFAULT_REDUCE_MOTION
                self.always_on_top = DEFAULT_ALWAYS_ON_TOP
                self.close_behavior = DEFAULT_CLOSE_BEHAVIOR
                self.quota_alert_threshold = DEFAULT_QUOTA_ALERT_THRESHOLD
                self.desktop_status_enabled = DEFAULT_DESKTOP_STATUS_ENABLED
                self.desktop_status_position = None
                self.desktop_status_style = DEFAULT_DESKTOP_STATUS_STYLE
                self.desktop_status_size = DEFAULT_DESKTOP_STATUS_SIZE
                self.lightweight_mode = DEFAULT_LIGHTWEIGHT_MODE
    
    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "language": self.language,
            "theme": self.theme,
            "statistics_timezone": self.statistics_timezone,
            "statistics_timezone_id": self.statistics_timezone_id,
            "auto_update": self.auto_update,
            "include_beta": self.include_beta,
            "active_runtime": self.active_runtime,
            "quota_display": self.quota_display,
            "model_scope": self.model_scope,
            "shortcut": self.shortcut,
            "reduce_motion": self.reduce_motion,
            "always_on_top": self.always_on_top,
            "close_behavior": self.close_behavior,
            "quota_alert_threshold": self.quota_alert_threshold,
            "desktop_status_enabled": self.desktop_status_enabled,
            "desktop_status_position": list(self.desktop_status_position) if self.desktop_status_position else None,
            "desktop_status_style": self.desktop_status_style,
            "desktop_status_size": self.desktop_status_size,
            "lightweight_mode": self.lightweight_mode,
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_listener(self, callback: Callable):
        self.listeners.append(callback)
    
    def _notify_listeners(self):
        for listener in self.listeners:
            listener()
