> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/settings-system.md)

# Settings System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a settings system that allows users to switch language (Chinese/English) and theme (auto/light/dark) with immediate effect.

**Architecture:** Create a settings manager, theme manager, and translation manager. Settings are stored in `~/.codexU/config.json`. UI components update immediately when settings change.

**Tech Stack:** PySide6, JSON, pathlib

## Global Constraints
- Python 3.8+
- PySide6
- Settings stored in `~/.codexU/config.json`
- Language options: "zh" (Chinese), "en" (English)
- Theme options: "auto", "light", "dark"
- All changes must take immediate effect without restart

---

## File Structure

**Create:**
- `app/utils/settings.py` - SettingsManager class
- `app/utils/theme.py` - ThemeManager class  
- `app/utils/translation.py` - TranslationManager class

**Modify:**
- `app/settings_dialog.py` - Connect signals to settings manager
- `app/main_window.py` - Load settings on startup
- `app/ui/dashboard.py` - Support dynamic text updates

**Test:**
- `tests/test_settings.py` - Test SettingsManager
- `tests/test_theme.py` - Test ThemeManager
- `tests/test_translation.py` - Test TranslationManager

---

### Task 1: Create Settings Manager

**Covers:** [S4]

**Files:**
- Create: `app/utils/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `SettingsManager` class with `get_language()`, `get_theme()`, `set_language()`, `set_theme()`, `load()`, `save()` methods

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.settings'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/utils/settings.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/utils/settings.py tests/test_settings.py
git commit -m "feat: add SettingsManager for loading and saving settings"
```

---

### Task 2: Create Translation Manager

**Covers:** [S6]

**Files:**
- Create: `app/utils/translation.py`
- Test: `tests/test_translation.py`

**Interfaces:**
- Consumes: `SettingsManager` (to get language)
- Produces: `TranslationManager` class with `tr(key)` method and `set_language()` method

- [ ] **Step 1: Write the failing test**

```python
# tests/test_translation.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_translation.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.translation'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/utils/translation.py
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
        "project_ranking": "机削排行",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_translation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/utils/translation.py tests/test_translation.py
git commit -m "feat: add TranslationManager for language switching"
```

---

### Task 3: Create Theme Manager

**Covers:** [S5]

**Files:**
- Create: `app/utils/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: `SettingsManager` (to get theme)
- Produces: `ThemeManager` class with `apply_theme()` method and `set_theme()` method

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.theme'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/utils/theme.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/utils/theme.py tests/test_theme.py
git commit -m "feat: add ThemeManager for theme switching"
```

---

### Task 4: Modify Settings Dialog

**Covers:** [S7]

**Files:**
- Modify: `app/settings_dialog.py`

**Interfaces:**
- Consumes: `SettingsManager`, `TranslationManager`, `ThemeManager`
- Produces: Updated settings dialog with connected signals

- [ ] **Step 1: Read current settings_dialog.py**

Read: `app/settings_dialog.py` to understand current structure.

- [ ] **Step 2: Add imports and modify constructor**

```python
# Add to imports
from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager

# Modify SettingsDialog constructor to accept managers
class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_manager: SettingsManager = None, 
                 translation_manager: TranslationManager = None, 
                 theme_manager: ThemeManager = None):
        super().__init__(parent)
        self.settings_manager = settings_manager or SettingsManager(Path.home() / ".codexU" / "config.json")
        self.translation_manager = translation_manager or TranslationManager()
        self.theme_manager = theme_manager or ThemeManager()
        
        # Connect signals
        self.settings_manager.add_listener(self._on_settings_changed)
        self.translation_manager.add_listener(self._on_language_changed)
        self.theme_manager.add_listener(self._on_theme_changed)
        
        # Rest of constructor...
```

- [ ] **Step 3: Modify _general_tab to connect language signal**

```python
def _general_tab(self):
    tab = QWidget()
    form = QFormLayout(tab)
    form.setSpacing(14)
    
    # Language combo with signal connection
    lang_combo = _combo(["中文", "English"])
    lang_combo.setCurrentIndex(0 if self.translation_manager.get_language() == "zh" else 1)
    lang_combo.currentIndexChanged.connect(self._on_language_changed)
    form.addRow("语言:", lang_combo)
    
    # Rest of tab...
    return tab
```

- [ ] **Step 4: Modify _display_tab to connect theme signal**

```python
def _display_tab(self):
    tab = QWidget()
    form = QFormLayout(tab)
    form.setSpacing(14)
    
    # Theme combo with signal connection
    theme_combo = _combo(["自动", "浅色", "深色"])
    theme_map = {"auto": 0, "light": 1, "dark": 2}
    theme_combo.setCurrentIndex(theme_map.get(self.theme_manager.get_theme(), 2))
    theme_combo.currentIndexChanged.connect(self._on_theme_changed)
    form.addRow("外观:", theme_combo)
    
    # Rest of tab...
    return tab
```

- [ ] **Step 5: Add signal handler methods**

```python
def _on_language_changed(self, index):
    lang = "zh" if index == 0 else "en"
    self.translation_manager.set_language(lang)
    self.settings_manager.set_language(lang)
    self.settings_manager.save()

def _on_theme_changed(self, index):
    theme_map = {0: "auto", 1: "light", 2: "dark"}
    theme = theme_map.get(index, "dark")
    self.theme_manager.set_theme(theme)
    self.settings_manager.set_theme(theme)
    self.settings_manager.save()

def _on_settings_changed(self):
    # Update UI with current settings
    pass
```

- [ ] **Step 6: Commit**

```bash
git add app/settings_dialog.py
git commit -m "feat: connect settings dialog to settings managers"
```

---

### Task 5: Modify Main Window

**Covers:** [S8]

**Files:**
- Modify: `app/main_window.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: `SettingsManager`, `TranslationManager`, `ThemeManager`
- Produces: Updated main window with settings loaded on startup

- [ ] **Step 1: Modify main.py to initialize managers**

```python
# main.py
from pathlib import Path
from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager

class CodexUApplication:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("codexU")
        self.app.setOrganizationName("codexU")
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyle("Fusion")
        self.app.setFont(QFont("Microsoft YaHei", 9))
        
        # Initialize managers
        config_path = Path.home() / ".codexU" / "config.json"
        self.settings_manager = SettingsManager(config_path)
        self.settings_manager.load()
        
        self.translation_manager = TranslationManager()
        self.translation_manager.set_language(self.settings_manager.get_language())
        
        self.theme_manager = ThemeManager()
        self.theme_manager.set_theme(self.settings_manager.get_theme())
        self.theme_manager.apply_theme(self.app)
        
        self.settings_dialog = None
        self.window = MainAppWindow(
            settings_manager=self.settings_manager,
            translation_manager=self.translation_manager,
            theme_manager=self.theme_manager
        )
        # Rest of constructor...
```

- [ ] **Step 2: Modify MainAppWindow to accept managers**

```python
# main_window.py
class MainAppWindow(QMainWindow):
    def __init__(self, parent=None, settings_manager=None, 
                 translation_manager=None, theme_manager=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.translation_manager = translation_manager
        self.theme_manager = theme_manager
        
        # Rest of constructor...
```

- [ ] **Step 3: Modify SettingsDialog instantiation**

```python
def _show_settings(self):
    if self.settings_dialog is None:
        self.settings_dialog = SettingsDialog(
            self.window,
            settings_manager=self.settings_manager,
            translation_manager=self.translation_manager,
            theme_manager=self.theme_manager
        )
    self.settings_dialog.show()
    self.settings_dialog.raise_()
    self.settings_dialog.activateWindow()
```

- [ ] **Step 4: Commit**

```bash
git add app/main_window.py main.py
git commit -m "feat: integrate settings managers into main application"
```

---

### Task 6: Update Dashboard for Dynamic Text

**Covers:** [S6, S7]

**Files:**
- Modify: `app/ui/dashboard.py`

**Interfaces:**
- Consumes: `TranslationManager`
- Produces: Updated dashboard with translatable text

- [ ] **Step 1: Add translation manager to DashboardWidget**

```python
# dashboard.py
class DashboardWidget(QWidget):
    open_settings = Signal()
    
    def __init__(self, parent=None, translation_manager=None):
        super().__init__(parent)
        self.translation_manager = translation_manager
        # Rest of constructor...
```

- [ ] **Step 2: Replace hardcoded strings with translation keys**

```python
# Replace hardcoded strings
title = QLabel(self.translation_manager.tr("codex") if self.translation_manager else "codexU")
self.codex_btn = QPushButton(self.translation_manager.tr("codex") if self.translation_manager else "Codex")
self.claude_btn = QPushButton(self.translation_manager.tr("claude_code") if self.translation_manager else "Claude Code")

# Tab names
self.tabs.addTab(self.task_tab, self.translation_manager.tr("today_tasks") if self.translation_manager else "☰ 今日任务")
self.tabs.addTab(self.trend_tab, self.translation_manager.tr("usage_trend") if self.translation_manager else "≡ 用量趋势")
self.tabs.addTab(self.project_tab, self.translation_manager.tr("project_ranking") if self.translation_manager else "机削排行")
self.tabs.addTab(self.heatmap_tab, self.translation_manager.tr("skill") if self.translation_manager else "Skill")
```

- [ ] **Step 3: Add method to update text dynamically**

```python
def update_text(self):
    if not self.translation_manager:
        return
    
    title = QLabel(self.translation_manager.tr("codex"))
    self.codex_btn.setText(self.translation_manager.tr("codex"))
    self.claude_btn.setText(self.translation_manager.tr("claude_code"))
    
    # Update tab names
    self.tabs.setTabText(0, self.translation_manager.tr("today_tasks"))
    self.tabs.setTabText(1, self.translation_manager.tr("usage_trend"))
    self.tabs.setTabText(2, self.translation_manager.tr("project_ranking"))
    self.tabs.setTabText(3, self.translation_manager.tr("skill"))
```

- [ ] **Step 4: Connect to translation manager**

```python
# In DashboardWidget.__init__
if self.translation_manager:
    self.translation_manager.add_listener(self.update_text)
```

- [ ] **Step 5: Commit**

```bash
git add app/ui/dashboard.py
git commit -m "feat: add dynamic text updates to dashboard"
```

---

### Task 7: Test Integration

**Covers:** [S9, S10]

**Files:**
- Test: `tests/test_integration.py`

**Interfaces:**
- Tests the complete settings system integration

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
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
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for settings system"
```

---

## Self-Review

**1. Spec coverage:** 
- [S4] Settings Manager - Task 1
- [S5] Theme Manager - Task 3
- [S6] Translation Manager - Task 2
- [S7] Settings Dialog Changes - Task 4
- [S8] Application Startup - Task 5
- [S9] Error Handling - Task 1 (in SettingsManager.load())
- [S10] Testing - Tasks 1-3, 7

All spec sections covered.

**2. Placeholder scan:** No placeholders found. All steps contain actual code.

**3. Type consistency:** 
- `SettingsManager` methods consistent across tasks
- `TranslationManager.tr()` method consistent
- `ThemeManager` methods consistent
- All managers use same callback pattern

No issues found.