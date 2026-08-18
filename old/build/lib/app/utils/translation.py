from __future__ import annotations
from typing import Callable

TRANSLATIONS = {
    "zh": {
        "settings": "设置",
        "language": "语言",
        "theme": "外观",
        "close": "关闭",
        "general": "通用",
        "display": "外观",
        "system": "系统",
        "auto_check_update": "自动检查 GitHub Release 更新",
        "receive_beta": "接收 Beta 版本",
        "status_bar": "状态栏",
        "display_mode": "展示模式",
        "simple": "简约",
        "classic": "经典",
        "rich": "丰富",
        "quota_diameter": "额度口径",
        "used": "已用量",
        "remaining": "剩余量",
        "reset_timer": "重置倒计时",
        "main_window_top": "主窗口置顶",
        "minimize_to_tray": "关闭时最小化到托盘",
        "system_status": "系统状态",
        "running": "运行中",
        "auto_check_update_system": "自动检查更新",
        "check_update": "检查更新",
        "version": "版本",
        "codex": "Codex",
        "claude_code": "Claude Code",
        "today": "今日",
        "last_7_days": "近 7 天",
        "cumulative": "累计",
        "羊毛进度": "羊毛进度",
        "today_tasks": "今日任务",
        "usage_trend": "用量趋势",
        "project_ranking": "项目排行",
        "skill": "Skill",
    },
    "en": {
        "settings": "Settings",
        "language": "Language",
        "theme": "Appearance",
        "close": "Close",
        "general": "General",
        "display": "Appearance",
        "system": "System",
        "auto_check_update": "Auto-check GitHub Release updates",
        "receive_beta": "Receive Beta versions",
        "status_bar": "Status Bar",
        "display_mode": "Display Mode",
        "simple": "Simple",
        "classic": "Classic",
        "rich": "Rich",
        "quota_diameter": "Quota Diameter",
        "used": "Used",
        "remaining": "Remaining",
        "reset_timer": "Reset Timer",
        "main_window_top": "Main Window Top",
        "minimize_to_tray": "Minimize to Tray on Close",
        "system_status": "System Status",
        "running": "Running",
        "auto_check_update_system": "Auto-check Updates",
        "check_update": "Check Updates",
        "version": "Version",
        "codex": "Codex",
        "claude_code": "Claude Code",
        "today": "Today",
        "last_7_days": "Last 7 Days",
        "cumulative": "Cumulative",
        "羊毛进度": "Wool Progress",
        "today_tasks": "Today's Tasks",
        "usage_trend": "Usage Trend",
        "project_ranking": "Project Ranking",
        "skill": "Skill",
    }
}

class TranslationManager:
    def __init__(self):
        self.language = "zh"
        self.listeners: list[Callable] = []
    
    def get_language(self) -> str:
        return self.language
    
    def set_language(self, lang: str):
        if lang in ("zh", "en"):
            self.language = lang
            self._notify_listeners()
    
    def tr(self, key: str) -> str:
        return TRANSLATIONS.get(self.language, {}).get(key, key)
    
    def add_listener(self, callback: Callable):
        self.listeners.append(callback)
    
    def _notify_listeners(self):
        for listener in self.listeners:
            listener()
