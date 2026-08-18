from __future__ import annotations

import sys
from typing import Callable, Optional

from PySide6.QtGui import QColor, QPalette

from app.utils.palette_manager import PaletteManager, PaletteTokens

DEFAULT_PALETTE = "codexu.default"
_LIQUID_GLASS_OPACITY = 0.78
_LIQUID_GLASS_BORDER_ALPHA = 0.12


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"rgba(0,0,0,{alpha})"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _token(token: Optional[str], fallback: str) -> str:
    return token or fallback


def _build_liquid_glass_qss(tokens: PaletteTokens, appearance: str) -> str:
    is_dark = appearance == "dark"
    accent = _token(tokens.accent.get("primary"), "#2866F7")
    accent_strong = _token(tokens.accent.get("primaryStrong"), "#1F59ED")
    accent_light = _token(tokens.accent.get("primaryLight"), "#7BA0FF")
    secondary = _token(tokens.accent.get("secondary"), "#8B6DFF")
    highlight = _token(tokens.accent.get("highlight"), "#DAA3FA")

    quota_primary_start = _token(tokens.quota.get("primary", {}).get("start"), accent_light)
    quota_primary_end = _token(tokens.quota.get("primary", {}).get("end"), accent_strong)
    quota_secondary_start = _token(tokens.quota.get("secondary", {}).get("start"), highlight)
    quota_secondary_end = _token(tokens.quota.get("secondary", {}).get("end"), secondary)

    token_input = _token(tokens.data.get("tokenInput"), accent)
    token_cached = _token(tokens.data.get("tokenCached"), secondary)
    token_output = _token(tokens.data.get("tokenOutput"), "#FF9F0A")

    series = tokens.data.get("series", [accent, secondary, highlight])
    series0 = _token(series[0] if len(series) > 0 else accent, accent)
    series1 = _token(series[1] if len(series) > 1 else secondary, secondary)
    series2 = _token(series[2] if len(series) > 2 else highlight, highlight)

    heatmap = tokens.data.get("heatmap", ["#0000001A", "#2866F747", "#2866F775", "#2866F7B3", "#2866F7F5"])
    heatmap0 = _token(heatmap[0] if heatmap else "#0000001A", "#0000001A")
    heatmap1 = _token(heatmap[1] if len(heatmap) > 1 else "#2866F747", "#2866F747")
    heatmap2 = _token(heatmap[2] if len(heatmap) > 2 else "#2866F775", "#2866F775")
    heatmap3 = _token(heatmap[3] if len(heatmap) > 3 else "#2866F7B3", "#2866F7B3")
    heatmap4 = _token(heatmap[4] if len(heatmap) > 4 else "#2866F7F5", "#2866F7F5")

    focus_ring = _token(tokens.selection.get("focusRing"), accent)
    surface_tint = _token(tokens.surface_tint.get("color"), accent)
    surface_tint_opacity = tokens.surface_tint.get("maximumOpacity", 0.08)

    if is_dark:
        background = _hex_to_rgba("#0f1117", _LIQUID_GLASS_OPACITY)
        surface = _hex_to_rgba("#1b202b", _LIQUID_GLASS_OPACITY)
        surface_tint_color = _hex_to_rgba(surface_tint, surface_tint_opacity)
        border = _hex_to_rgba("#2b3548", _LIQUID_GLASS_BORDER_ALPHA)
        text_primary = "#f5f7fb"
        text_secondary = "#94a3b8"
        text_muted = "#748197"
        text_inverse = "#172033"
        card_hover_border = _hex_to_rgba(accent, 0.25)
        selection_bg = _hex_to_rgba(accent, 0.18)
    else:
        background = _hex_to_rgba("#f4f6fb", _LIQUID_GLASS_OPACITY)
        surface = _hex_to_rgba("#ffffff", _LIQUID_GLASS_OPACITY)
        surface_tint_color = _hex_to_rgba(surface_tint, surface_tint_opacity)
        border = _hex_to_rgba("#dce4f0", _LIQUID_GLASS_BORDER_ALPHA)
        text_primary = "#172033"
        text_secondary = "#526071"
        text_muted = "#8a94a6"
        text_inverse = "#f5f7fb"
        card_hover_border = _hex_to_rgba(accent, 0.35)
        selection_bg = _hex_to_rgba(accent, 0.12)

    return f"""
* {{ font-family: 'Microsoft YaHei'; }}
QMainWindow, QDialog {{ background: {background}; color: {text_primary}; }}
QWidget {{ color: {text_primary}; }}
QWidget#dashboard, QWidget#centralWidget {{ background: qradialgradient(cx:0.82, cy:0.02, radius:1.1, fx:0.82, fy:0.02, stop:0 {surface_tint_color}, stop:0.34 {surface}, stop:1 {background}); }}
QFrame#surfaceCard {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#summaryPanel {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
QFrame#tabPanel {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
QFrame#subtleCard {{ background: {surface}; border: 1px solid {border}; border-radius: 9px; }}
QFrame#quotaGroup {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QGroupBox#surfaceCard {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; margin-top: 12px; padding-top: 8px; font-weight: 700; }}
QGroupBox#surfaceCard::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {text_primary}; }}
QFrame#taskCard, QFrame#projectRow {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#recentProjectRow {{ background: {surface}; border: 0; border-radius: 6px; }}
QFrame#projectUsageRow {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#projectUsageRow:hover {{ background: {selection_bg}; border-color: {card_hover_border}; }}
QFrame#overviewMetric {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QDialog#projectDetailDialog {{ background: {background}; }}
QFrame#detailRow {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#detailRow:hover {{ background: {selection_bg}; border-color: {card_hover_border}; }}
QLabel#projectRank {{ color: {text_secondary}; font-size: 10px; }}
QLabel#projectName {{ color: {text_primary}; font-size: 11px; font-weight: 600; }}
QLabel#projectToken {{ color: {text_primary}; font-size: 12px; font-weight: 700; }}
QLabel#overviewValue {{ color: {text_primary}; font-size: 18px; font-weight: 700; }}
QLabel#countBadge {{ background: {selection_bg}; color: {text_secondary}; border: 0; border-radius: 7px; padding: 4px 8px; font-size: 10px; }}
QLabel#projectMarker {{ background: {selection_bg}; border: 1px solid {card_hover_border}; border-radius: 6px; }}
QProgressBar#projectBar {{ background: {border}; border: 0; border-radius: 2px; }}
QProgressBar#projectBar::chunk {{ background: {series0}; border-radius: 2px; }}
QFrame#usageRow {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#topControlGroup {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#statStrip {{ background: {surface}; border: 0; border-radius: 10px; }}
QFrame#statDivider {{ color: {border}; }}
QFrame#taskCard:hover, QFrame#projectRow:hover {{ background: {selection_bg}; border-color: {card_hover_border}; }}
QLabel#pageTitle {{ color: {text_primary}; font-size: 22px; font-weight: 700; }}
QLabel#pageSubtitle {{ color: {text_secondary}; font-size: 11px; }}
QLabel#sectionTitle {{ color: {text_primary}; font-size: 14px; font-weight: 700; }}
QLabel#muted {{ color: {text_secondary}; }}
QLabel#caption {{ color: {text_muted}; font-size: 10px; }}
QLabel#metricValue {{ color: {text_primary}; font-family: 'Segoe UI Variable Display'; font-size: 27px; font-weight: 700; }}
QLabel#metricLabel {{ color: {text_secondary}; font-size: 11px; }}
QLabel#metricHint {{ color: {text_muted}; font-size: 10px; }}
QLabel#metricBreakdown {{ color: {text_secondary}; font-size: 9px; }}
QFrame#modelUsageRow {{ background: {surface}; border: 1px solid {border}; border-radius: 9px; }}
QFrame#modelUsageRow:hover {{ background: {selection_bg}; border-color: {card_hover_border}; }}
QFrame#modelUsageRow[selected="true"] {{ background: {selection_bg}; border-color: {focus_ring}; }}
QLabel#modelUsageName {{ color: {text_primary}; font-size: 11px; font-weight: 650; }}
QLabel#modelUsageValue {{ color: {text_primary}; font-family: 'Segoe UI Variable Display'; font-size: 13px; font-weight: 700; }}
QFrame#modelMetricTile {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#modelMetricTile[tone="uncachedMetric"] {{ border-left: 3px solid {token_input}; }}
QFrame#modelMetricTile[tone="cachedMetric"] {{ border-left: 3px solid {token_cached}; }}
QFrame#modelMetricTile[tone="outputMetric"] {{ border-left: 3px solid {token_output}; }}
QLabel#modelMetricValue {{ color: {text_primary}; font-family: 'Segoe UI Variable Display'; font-size: 14px; font-weight: 720; }}
QProgressBar#modelUsageProgress {{ background: {border}; border: 0; border-radius: 3px; }}
QProgressBar#modelUsageProgress::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {series0},stop:1 {series1}); border-radius: 3px; }}
QLabel#brandMark {{ color: {accent_light}; font-size: 20px; font-weight: 700; }}
QLabel#brandName {{ color: {text_primary}; font-family: 'Segoe UI Variable Display'; font-size: 17px; font-weight: 700; }}
QLabel#brandSubtitle {{ color: {text_muted}; font-size: 10px; }}
QToolButton#navButton {{ background: transparent; color: {text_secondary}; border: 0; border-radius: 7px; padding: 9px 12px; text-align: left; font-size: 12px; }}
QToolButton#navButton:hover {{ background: {selection_bg}; color: {text_primary}; }}
QToolButton#navButton:checked {{ background: {selection_bg}; color: {text_primary}; border: 1px solid {focus_ring}; }}
QPushButton#runtimeButton {{ background: {surface}; color: {text_secondary}; border: 1px solid {border}; border-radius: 7px; padding: 7px 13px; font-weight: 600; }}
QPushButton#runtimeButton:hover {{ background: {selection_bg}; color: {text_primary}; border-color: {card_hover_border}; }}
QPushButton#runtimeButton:checked {{ background: {selection_bg}; border-color: {focus_ring}; color: {text_primary}; }}
QPushButton#tabButton {{ background: transparent; color: {text_secondary}; border: 0; border-radius: 8px; padding: 9px 16px; font-weight: 600; }}
QPushButton#tabButton:hover {{ background: {selection_bg}; color: {text_primary}; }}
QPushButton#tabButton:checked {{ background: {selection_bg}; color: {text_primary}; }}
QFrame#tabIndicator {{ background: {focus_ring}; border: 0; border-radius: 8px; }}
QPushButton#animatedTabButton {{ background: transparent; color: {text_secondary}; border: 0; padding: 8px 12px; font-weight: 600; }}
QPushButton#animatedTabButton:hover {{ color: {text_primary}; }}
QPushButton#animatedTabButton:checked {{ color: {text_primary}; }}
QPushButton#topToggleButton {{ background: transparent; color: {text_secondary}; border: 0; border-radius: 6px; padding: 0; font-weight: 700; }}
QPushButton#topToggleButton:hover {{ background: {selection_bg}; color: {text_primary}; }}
QPushButton#topToggleButton:checked {{ background: {selection_bg}; color: {text_primary}; }}
QPushButton#topToggleButton:focus {{ outline: 2px solid {focus_ring}; outline-offset: 2px; }}
QPushButton#quotaToggle {{ background: transparent; color: {text_secondary}; border: 0; border-radius: 6px; padding: 3px 6px; font-size: 9px; }}
QPushButton#quotaToggle:hover {{ color: {text_primary}; background: {selection_bg}; }}
QPushButton#quotaToggle:checked {{ color: {text_primary}; background: {selection_bg}; }}
QPushButton#quotaToggle:focus {{ outline: 2px solid {focus_ring}; outline-offset: 2px; }}
QPushButton#miniTabButton {{ background: transparent; color: {text_secondary}; border: 0; border-radius: 6px; padding: 6px 11px; }}
QPushButton#miniTabButton:hover {{ background: {selection_bg}; color: {text_primary}; }}
QPushButton#miniTabButton:checked {{ background: {selection_bg}; color: {text_primary}; font-weight: 700; }}
QPushButton#miniTabButton:focus {{ outline: 2px solid {focus_ring}; outline-offset: 2px; }}
QLabel#planBadge {{ background: {selection_bg}; color: {text_primary}; border: 1px solid {card_hover_border}; border-radius: 16px; font-weight: 700; }}
QLabel#statusPill {{ background: {surface}; color: {accent_light}; border: 1px solid {card_hover_border}; border-radius: 8px; padding: 5px 9px; font-size: 10px; }}
QFrame#rangeStrip {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
QLabel#rangeValue {{ color: {text_primary}; font-family: 'Segoe UI Variable'; font-size: 10px; font-weight: 700; }}
QFrame#quotaResetStrip {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#quotaResetDivider {{ background: {border}; max-width: 1px; }}
QLabel#quotaResetTime {{ color: {text_primary}; font-family: 'Segoe UI Variable Display'; font-size: 16px; font-weight: 700; }}
QLabel#positiveBadge {{ background: {selection_bg}; color: {series0}; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }}
QLabel#negativeBadge {{ background: {selection_bg}; color: {series2}; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }}
QLabel#neutralBadge {{ background: {selection_bg}; color: {text_secondary}; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }}
QWidget#desktopStatusPanel {{ background: transparent; }}
QFrame#desktopStatusShell {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
QLabel#desktopStatusValue {{ color: {text_primary}; font-family: "Segoe UI Variable"; font-size: 22px; font-weight: 700; }}
QLabel#desktopStatusQuota {{ color: {text_secondary}; background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 7px 8px; }}
QPushButton#desktopStatusButton {{ background: {surface}; color: {text_primary}; border: 1px solid {border}; border-radius: 6px; padding: 4px 8px; font-size: 10px; }}
QPushButton#desktopStatusButton:hover {{ background: {selection_bg}; border-color: {focus_ring}; }}
QLabel#diagnosticText {{ color: {text_secondary}; background: {surface}; border: 1px solid {border}; border-radius: 8px; padding: 10px; line-height: 1.4; }}
QPushButton#iconButton, QToolButton#iconButton {{ background: {surface}; color: {text_secondary}; border: 1px solid {border}; border-radius: 7px; padding: 6px; }}
QPushButton#iconButton:hover, QToolButton#iconButton:hover {{ background: {selection_bg}; color: {text_primary}; }}
QPushButton#iconButton:focus, QToolButton#iconButton:focus {{ outline: 2px solid {focus_ring}; outline-offset: 2px; }}
QPushButton#primaryButton {{ background: {accent}; color: {text_inverse}; border: 0; border-radius: 7px; padding: 7px 13px; font-weight: 600; }}
QPushButton#primaryButton:hover {{ background: {accent_strong}; }}
QPushButton#primaryButton:focus {{ outline: 2px solid {focus_ring}; outline-offset: 2px; }}
QProgressBar {{ background: {border}; border: 0; border-radius: 4px; text-align: right; color: {text_secondary}; }}
QProgressBar::chunk {{ background: {series0}; border-radius: 4px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ width: 8px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QComboBox, QLineEdit {{ background: {surface}; color: {text_primary}; border: 1px solid {border}; border-radius: 8px; padding: 7px 10px; min-height: 20px; }}
QComboBox {{ padding-right: 36px; }}
QComboBox:hover {{ border-color: {card_hover_border}; background: {selection_bg}; }}
QComboBox:focus, QComboBox:on {{ border-color: {focus_ring}; }}
QComboBox:focus {{ outline: 2px solid {focus_ring}; outline-offset: 1px; }}
QLineEdit:focus {{ outline: 2px solid {focus_ring}; outline-offset: 1px; border-color: {focus_ring}; }}
QPushButton:focus {{ outline: 2px solid {focus_ring}; outline-offset: 2px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 32px; border: 0; border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: transparent; }}
QComboBox::drop-down:hover {{ background: {selection_bg}; }}
QComboBox::down-arrow {{ image: url(Resources/icons/chevron-down.svg); width: 12px; height: 8px; }}
QListView#comboPopup {{ background: {surface}; color: {text_primary}; border: 1px solid {border}; border-radius: 10px; padding: 5px; outline: 0; }}
QListView#comboPopup::item {{ border: 0; border-radius: 6px; padding: 6px 10px; }}
QListView#comboPopup::item:hover {{ background: {selection_bg}; }}
QListView#comboPopup::item:selected {{ background: {accent}; color: {text_inverse}; }}
QPushButton#shortcutRecorder {{ background: {surface}; color: {text_primary}; border: 1px solid {border}; border-radius: 8px; padding: 7px 12px; text-align: left; }}
QPushButton#shortcutRecorder:hover, QPushButton#shortcutRecorder:focus {{ border-color: {focus_ring}; background: {selection_bg}; }}
QTabWidget::pane {{ border: 0; background: transparent; }}
QTabBar::tab {{ background: transparent; color: {text_secondary}; padding: 7px 12px; }}
QTabBar::tab:selected {{ color: {text_primary}; border-bottom: 2px solid {focus_ring}; }}
QCheckBox {{ color: {text_secondary}; }}
QMenu {{ background: {surface}; color: {text_primary}; border: 1px solid {border}; }}
QMenu::item {{ padding: 7px 18px; }}
QMenu::item:selected {{ background: {selection_bg}; }}
"""

class ThemeManager:
    def __init__(self, palette_manager: Optional[PaletteManager] = None):
        self.theme = "dark"
        self.palette_manager = palette_manager or PaletteManager()
        self.listeners: list[Callable] = []

    def get_theme(self) -> str:
        return self.theme

    def set_theme(self, theme: str):
        if not isinstance(theme, str):
            return
        if theme in ("auto", "light", "dark") or theme.startswith("palette."):
            self.theme = theme
            self._notify_listeners()

    def get_stylesheet(self) -> str:
        if self.theme.startswith("palette."):
            palette_id = self.theme.split(".", maxsplit=1)[1]
            if self.palette_manager.load(palette_id, self.palette_manager.current_appearance):
                tokens = self.palette_manager.current_tokens
                appearance = self.palette_manager.current_appearance
                return _build_liquid_glass_qss(tokens, appearance)
        appearance = self.get_effective_theme()
        self.palette_manager.load(DEFAULT_PALETTE, appearance)
        return _build_liquid_glass_qss(self.palette_manager.current_tokens, self.palette_manager.current_appearance)

    def get_effective_theme(self) -> str:
        if self.theme.startswith("palette."):
            return self.palette_manager.current_appearance
        return self._detect_system_theme() if self.theme == "auto" else self.theme

    def apply_theme(self, app):
        effective = self.get_effective_theme()
        palette = QPalette()
        if effective == "dark":
            palette.setColor(QPalette.ColorRole.Window, QColor("#0f1117"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#f5f7fb"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#171b24"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#f5f7fb"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#171d27"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f5f7fb"))
        else:
            palette.setColor(QPalette.ColorRole.Window, QColor("#f4f6fb"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f2937"))
            palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#1f2937"))
            palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1f2937"))
        app.setPalette(palette)
        app.setStyleSheet(self.get_stylesheet())

    def _detect_system_theme(self) -> str:
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                winreg.CloseKey(key)
                return "light" if value == 1 else "dark"
            except Exception:
                return "dark"
        return "dark"

    def get_palette_color(self, token_path: str, fallback: str) -> str:
        appearance = self.get_effective_theme()
        palette_id = (
            self.theme.split(".", maxsplit=1)[1]
            if self.theme.startswith("palette.")
            else DEFAULT_PALETTE
        )
        current = self.palette_manager.current_tokens
        if current.palette_id != palette_id or current.appearance != appearance:
            self.palette_manager.load(palette_id, appearance)
        value = self.palette_manager.current_tokens.get(token_path, None)
        return value if isinstance(value, str) else fallback

    def add_listener(self, callback: Callable):
        self.listeners.append(callback)

    def _notify_listeners(self):
        for listener in self.listeners:
            listener()
