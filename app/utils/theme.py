from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtGui import QColor, QPalette


DARK_THEME = """
* { font-family: 'Microsoft YaHei'; }
QMainWindow, QDialog { background: #0f1117; color: #f5f7fb; }
QWidget { color: #f5f7fb; }
QWidget#dashboard, QWidget#centralWidget { background: qradialgradient(cx:0.82, cy:0.02, radius:1.1, fx:0.82, fy:0.02, stop:0 #19233a, stop:0.34 #111722, stop:1 #0f1117); }
QFrame#surfaceCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1b202b,stop:1 #161b24); border: 1px solid #2b3548; border-radius: 12px; }
QFrame#summaryPanel { background: rgba(17, 23, 34, 224); border: 1px solid #202b3d; border-radius: 14px; }
QFrame#tabPanel { background: rgba(17, 23, 34, 224); border: 1px solid #202b3d; border-radius: 14px; }
QFrame#subtleCard { background: #121720; border: 1px solid #232c3b; border-radius: 9px; }
QFrame#quotaGroup { background: #121720; border: 1px solid #232c3b; border-radius: 8px; }
QGroupBox#surfaceCard { background: #171b24; border: 1px solid #283142; border-radius: 10px; margin-top: 12px; padding-top: 8px; font-weight: 700; }
QGroupBox#surfaceCard::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #f5f7fb; }
QFrame#taskCard, QFrame#projectRow { background: #1a202b; border: 1px solid #263142; border-radius: 8px; }
QFrame#recentProjectRow { background: #121720; border: 0; border-radius: 6px; }
QFrame#projectUsageRow { background: #1a202b; border: 1px solid #263142; border-radius: 8px; }
QFrame#projectUsageRow:hover { background: #202a39; border-color: #3b5277; }
QFrame#overviewMetric { background: #1a202b; border: 1px solid #263142; border-radius: 8px; }
QDialog#projectDetailDialog { background: #111720; }
QFrame#detailRow { background: #171d27; border: 1px solid #2b3546; border-radius: 8px; }
QFrame#detailRow:hover { background: #202a39; border-color: #3b5277; }
QLabel#projectRank { color: #748197; font-size: 10px; }
QLabel#projectName { color: #f5f7fb; font-size: 11px; font-weight: 600; }
QLabel#projectToken { color: #f8fafc; font-size: 12px; font-weight: 700; }
QLabel#overviewValue { color: #f8fafc; font-size: 18px; font-weight: 700; }
QLabel#countBadge { background: #252d3b; color: #aab6c8; border: 0; border-radius: 7px; padding: 4px 8px; font-size: 10px; }
QLabel#projectMarker { background: #263751; border: 1px solid #35527e; border-radius: 6px; }
QProgressBar#projectBar { background: #283142; border: 0; border-radius: 2px; }
QProgressBar#projectBar::chunk { background: #6d72f6; border-radius: 2px; }
QFrame#usageRow { background: #121720; border: 1px solid #232c3b; border-radius: 8px; }
QFrame#topControlGroup { background: #171d27; border: 1px solid #2b3546; border-radius: 8px; }
QFrame#statStrip { background: #171b24; border: 0; border-radius: 10px; }
QFrame#statDivider { color: #2b3546; }
QFrame#taskCard:hover, QFrame#projectRow:hover { background: #202a39; border-color: #3b5277; }
QLabel#pageTitle { color: #f8fafc; font-size: 22px; font-weight: 700; }
QLabel#pageSubtitle { color: #91a0b7; font-size: 11px; }
QLabel#sectionTitle { color: #f5f7fb; font-size: 14px; font-weight: 700; }
QLabel#muted { color: #91a0b7; }
QLabel#caption { color: #748197; font-size: 10px; }
QLabel#metricValue { color: #f8fafc; font-family: 'Segoe UI Variable Display'; font-size: 27px; font-weight: 700; }
QLabel#metricLabel { color: #aab6c8; font-size: 11px; }
QLabel#metricHint { color: #748197; font-size: 10px; }
QLabel#metricBreakdown { color: #9aa8bd; font-size: 9px; }
QFrame#modelUsageRow { background: #151b25; border: 1px solid #283246; border-radius: 9px; }
QFrame#modelUsageRow:hover { background: #1d2736; border-color: #425a80; }
QFrame#modelUsageRow[selected="true"] { background: #202d45; border-color: #5e91f4; }
QLabel#modelUsageName { color: #f3f6fb; font-size: 11px; font-weight: 650; }
QLabel#modelUsageValue { color: #f8fafc; font-family: 'Segoe UI Variable Display'; font-size: 13px; font-weight: 700; }
QProgressBar#modelUsageProgress { background: #2b3445; border: 0; border-radius: 3px; }
QProgressBar#modelUsageProgress::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #398cf0,stop:1 #8d74ff); border-radius: 3px; }
QLabel#brandMark { color: #76a7ff; font-size: 20px; font-weight: 700; }
QLabel#brandName { color: #f8fafc; font-family: 'Segoe UI Variable Display'; font-size: 17px; font-weight: 700; }
QLabel#brandSubtitle { color: #748197; font-size: 10px; }
QToolButton#navButton { background: transparent; color: #91a0b7; border: 0; border-radius: 7px; padding: 9px 12px; text-align: left; font-size: 12px; }
QToolButton#navButton:hover { background: #1f2734; color: #e7edf7; }
QToolButton#navButton:checked { background: #243a63; color: #ffffff; }
QPushButton#runtimeButton { background: #1a202b; color: #91a0b7; border: 1px solid #2b3546; border-radius: 7px; padding: 7px 13px; font-weight: 600; }
QPushButton#runtimeButton:hover { background: #222b3a; color: #e7edf7; }
QPushButton#runtimeButton:checked { background: #315ba0; border-color: #6d9dff; color: #ffffff; }
QPushButton#tabButton { background: transparent; color: #91a0b7; border: 0; border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton#tabButton:hover { background: #1f2734; color: #e7edf7; }
QPushButton#tabButton:checked { background: #2b3f64; color: #ffffff; }
QFrame#tabIndicator { background: #2b3f64; border: 0; border-radius: 8px; }
QPushButton#animatedTabButton { background: transparent; color: #91a0b7; border: 0; padding: 8px 12px; font-weight: 600; }
QPushButton#animatedTabButton:hover { color: #e7edf7; }
QPushButton#animatedTabButton:checked { color: #ffffff; }
QPushButton#topToggleButton { background: transparent; color: #91a0b7; border: 0; border-radius: 6px; padding: 0; font-weight: 700; }
QPushButton#topToggleButton:hover { background: #243044; color: #ffffff; }
QPushButton#topToggleButton:checked { background: #315ba0; color: #ffffff; }
QPushButton#quotaToggle { background: transparent; color: #748197; border: 0; border-radius: 6px; padding: 3px 6px; font-size: 9px; }
QPushButton#quotaToggle:hover { color: #dce6f5; background: #202a39; }
QPushButton#quotaToggle:checked { color: #ffffff; background: #315ba0; }
QPushButton#miniTabButton { background: transparent; color: #91a0b7; border: 0; border-radius: 6px; padding: 6px 11px; }
QPushButton#miniTabButton:hover { background: #1f2734; color: #ffffff; }
QPushButton#miniTabButton:checked { background: #2b3f64; color: #ffffff; font-weight: 700; }
QLabel#planBadge { background: #252d3b; color: #dbe4f3; border: 1px solid #354157; border-radius: 16px; font-weight: 700; }
QLabel#statusPill { background: #1d2a3b; color: #9fc1ff; border: 1px solid #30435f; border-radius: 8px; padding: 5px 9px; font-size: 10px; }
QLabel#positiveBadge { background: #16382d; color: #55d89a; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }
QLabel#negativeBadge { background: #40252b; color: #ff8190; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }
QLabel#neutralBadge { background: #252d3b; color: #aab6c8; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }
QWidget#desktopStatusPanel { background: transparent; }
QFrame#desktopStatusShell { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1d2636,stop:0.65 #161d2a,stop:1 #151924); border: 1px solid #3a4c68; border-radius: 14px; }
QLabel#desktopStatusValue { color: #f5f8ff; font-family: "Segoe UI Variable"; font-size: 22px; font-weight: 700; }
QLabel#desktopStatusQuota { color: #a9c2eb; background: #111721; border: 1px solid #2c3b52; border-radius: 7px; padding: 7px 8px; }
QPushButton#desktopStatusButton { background: #263650; color: #dce8ff; border: 1px solid #3f5678; border-radius: 6px; padding: 4px 8px; font-size: 10px; }
QPushButton#desktopStatusButton:hover { background: #34517e; border-color: #5e91f4; }
QLabel#diagnosticText { color: #aab6c8; background: #121720; border: 1px solid #283142; border-radius: 8px; padding: 10px; line-height: 1.4; }
QPushButton#iconButton, QToolButton#iconButton { background: #171d27; color: #aab6c8; border: 1px solid #2b3546; border-radius: 7px; padding: 6px; }
QPushButton#iconButton:hover, QToolButton#iconButton:hover { background: #243044; color: #ffffff; }
QPushButton#primaryButton { background: #3c6dcc; color: #ffffff; border: 0; border-radius: 7px; padding: 7px 13px; font-weight: 600; }
QPushButton#primaryButton:hover { background: #4b7de0; }
QProgressBar { background: #252e3d; border: 0; border-radius: 4px; text-align: right; color: #91a0b7; }
QProgressBar::chunk { background: #5e91f4; border-radius: 4px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #344155; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox, QLineEdit { background: #171d27; color: #e7edf7; border: 1px solid #2b3546; border-radius: 8px; padding: 7px 10px; min-height: 20px; }
QComboBox { padding-right: 36px; }
QComboBox:hover { border-color: #455772; background: #1b2330; }
QComboBox:focus, QComboBox:on { border-color: #5e91f4; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 32px; border: 0; border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: transparent; }
QComboBox::drop-down:hover { background: #243044; }
QComboBox::down-arrow { image: url(resources/icons/chevron-down.svg); width: 12px; height: 8px; }
QListView#comboPopup { background: #171d27; color: #e7edf7; border: 1px solid #354157; border-radius: 10px; padding: 5px; outline: 0; }
QListView#comboPopup::item { border: 0; border-radius: 6px; padding: 6px 10px; }
QListView#comboPopup::item:hover { background: #243044; }
QListView#comboPopup::item:selected { background: #315ba0; color: #ffffff; }
QPushButton#shortcutRecorder { background: #171d27; color: #e7edf7; border: 1px solid #2b3546; border-radius: 8px; padding: 7px 12px; text-align: left; }
QPushButton#shortcutRecorder:hover, QPushButton#shortcutRecorder:focus { border-color: #5e91f4; background: #1b2330; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab { background: transparent; color: #91a0b7; padding: 7px 12px; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #6d9dff; }
QCheckBox { color: #aab6c8; }
QMenu { background: #171d27; color: #e7edf7; border: 1px solid #2b3546; }
QMenu::item { padding: 7px 18px; }
QMenu::item:selected { background: #315ba0; }
"""


LIGHT_THEME = """
* { font-family: 'Microsoft YaHei'; }
QMainWindow, QDialog { background: #f4f6fb; color: #1f2937; }
QWidget { color: #1f2937; }
QWidget#dashboard, QWidget#centralWidget { background: qradialgradient(cx:0.82, cy:0.02, radius:1.08, fx:0.82, fy:0.02, stop:0 #e3eaff, stop:0.38 #f0f4fc, stop:1 #f5f7fb); }
QFrame#surfaceCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #fbfcff); border: 1px solid #dce4f0; border-radius: 12px; }
QFrame#summaryPanel { background: rgba(238, 243, 255, 232); border: 1px solid #d9e3f4; border-radius: 14px; }
QFrame#tabPanel { background: rgba(238, 243, 255, 232); border: 1px solid #d9e3f4; border-radius: 14px; }
QFrame#subtleCard { background: #f8fafc; border: 1px solid #e5eaf1; border-radius: 9px; }
QFrame#quotaGroup { background: #f8fafc; border: 1px solid #e5eaf1; border-radius: 8px; }
QGroupBox#surfaceCard { background: #ffffff; border: 1px solid #dfe5ee; border-radius: 10px; margin-top: 12px; padding-top: 8px; font-weight: 700; }
QGroupBox#surfaceCard::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #1f2937; }
QFrame#taskCard, QFrame#projectRow { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
QFrame#recentProjectRow { background: #f8fafc; border: 0; border-radius: 6px; }
QFrame#projectUsageRow { background: #f8faff; border: 1px solid #e2e8f2; border-radius: 8px; }
QFrame#projectUsageRow:hover { background: #f2f6ff; border-color: #b7ccec; }
QFrame#overviewMetric { background: #f8faff; border: 1px solid #e2e8f2; border-radius: 8px; }
QDialog#projectDetailDialog { background: #f4f7fc; }
QFrame#detailRow { background: #f8faff; border: 1px solid #e2e8f2; border-radius: 8px; }
QFrame#detailRow:hover { background: #f2f6ff; border-color: #b7ccec; }
QLabel#projectRank { color: #8a94a6; font-size: 10px; }
QLabel#projectName { color: #26344b; font-size: 11px; font-weight: 600; }
QLabel#projectToken { color: #172033; font-size: 12px; font-weight: 700; }
QLabel#overviewValue { color: #172033; font-size: 18px; font-weight: 700; }
QLabel#countBadge { background: #edf2fb; color: #526071; border: 0; border-radius: 7px; padding: 4px 8px; font-size: 10px; }
QLabel#projectMarker { background: #e2ecff; border: 1px solid #c5d9fa; border-radius: 6px; }
QProgressBar#projectBar { background: #e6eaf2; border: 0; border-radius: 2px; }
QProgressBar#projectBar::chunk { background: #7777f4; border-radius: 2px; }
QFrame#usageRow { background: #f8fafc; border: 1px solid #e5eaf1; border-radius: 8px; }
QFrame#topControlGroup { background: #ffffff; border: 1px solid #d7dfeb; border-radius: 8px; }
QFrame#statStrip { background: #ffffff; border: 0; border-radius: 10px; }
QFrame#statDivider { color: #e2e8f0; }
QFrame#taskCard:hover, QFrame#projectRow:hover { background: #f7faff; border-color: #b7ccec; }
QLabel#pageTitle { color: #172033; font-size: 22px; font-weight: 700; }
QLabel#pageSubtitle { color: #667085; font-size: 11px; }
QLabel#sectionTitle { color: #1f2937; font-size: 14px; font-weight: 700; }
QLabel#muted { color: #667085; }
QLabel#caption { color: #8a94a6; font-size: 10px; }
QLabel#metricValue { color: #172033; font-family: 'Segoe UI Variable Display'; font-size: 27px; font-weight: 700; }
QLabel#metricLabel { color: #526071; font-size: 11px; }
QLabel#metricHint { color: #8a94a6; font-size: 10px; }
QLabel#metricBreakdown { color: #667085; font-size: 9px; }
QFrame#modelUsageRow { background: #f8faff; border: 1px solid #dfe6f2; border-radius: 9px; }
QFrame#modelUsageRow:hover { background: #f1f6ff; border-color: #b7ccec; }
QFrame#modelUsageRow[selected="true"] { background: #eaf2ff; border-color: #6d9dff; }
QLabel#modelUsageName { color: #26344b; font-size: 11px; font-weight: 650; }
QLabel#modelUsageValue { color: #172033; font-family: 'Segoe UI Variable Display'; font-size: 13px; font-weight: 700; }
QProgressBar#modelUsageProgress { background: #e3e9f2; border: 0; border-radius: 3px; }
QProgressBar#modelUsageProgress::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #398cf0,stop:1 #8d74ff); border-radius: 3px; }
QLabel#brandMark { color: #326ad6; font-size: 20px; font-weight: 700; }
QLabel#brandName { color: #172033; font-family: 'Segoe UI Variable Display'; font-size: 17px; font-weight: 700; }
QLabel#brandSubtitle { color: #8a94a6; font-size: 10px; }
QToolButton#navButton { background: transparent; color: #667085; border: 0; border-radius: 7px; padding: 9px 12px; text-align: left; font-size: 12px; }
QToolButton#navButton:hover { background: #e9eef7; color: #26344b; }
QToolButton#navButton:checked { background: #dbe8ff; color: #1d54b1; }
QPushButton#runtimeButton { background: #ffffff; color: #667085; border: 1px solid #d7dfeb; border-radius: 7px; padding: 7px 13px; font-weight: 600; }
QPushButton#runtimeButton:hover { background: #f1f5fb; color: #26344b; }
QPushButton#runtimeButton:checked { background: #dbe8ff; border-color: #7da7ee; color: #1d54b1; }
QPushButton#tabButton { background: transparent; color: #667085; border: 0; border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton#tabButton:hover { background: #e4ebf7; color: #26344b; }
QPushButton#tabButton:checked { background: #d6e3f8; color: #1d54b1; }
QFrame#tabIndicator { background: #d6e3f8; border: 0; border-radius: 8px; }
QPushButton#animatedTabButton { background: transparent; color: #667085; border: 0; padding: 8px 12px; font-weight: 600; }
QPushButton#animatedTabButton:hover { color: #26344b; }
QPushButton#animatedTabButton:checked { color: #1d54b1; }
QPushButton#topToggleButton { background: transparent; color: #667085; border: 0; border-radius: 6px; padding: 0; font-weight: 700; }
QPushButton#topToggleButton:hover { background: #edf2f9; color: #26344b; }
QPushButton#topToggleButton:checked { background: #3987ef; color: #ffffff; }
QPushButton#quotaToggle { background: transparent; color: #8a94a6; border: 0; border-radius: 6px; padding: 3px 6px; font-size: 9px; }
QPushButton#quotaToggle:hover { color: #26344b; background: #edf2f9; }
QPushButton#quotaToggle:checked { color: #1d54b1; background: #dbe8ff; }
QPushButton#miniTabButton { background: transparent; color: #667085; border: 0; border-radius: 6px; padding: 6px 11px; }
QPushButton#miniTabButton:hover { background: #edf2f9; color: #26344b; }
QPushButton#miniTabButton:checked { background: #dbe8ff; color: #1d54b1; font-weight: 700; }
QLabel#planBadge { background: #ffffff; color: #526071; border: 1px solid #d7dfeb; border-radius: 16px; font-weight: 700; }
QLabel#statusPill { background: #e8f1ff; color: #285fbd; border: 1px solid #c8daf8; border-radius: 8px; padding: 5px 9px; font-size: 10px; }
QLabel#positiveBadge { background: #e3f7ee; color: #18845c; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }
QLabel#negativeBadge { background: #fff0f1; color: #c44756; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }
QLabel#neutralBadge { background: #edf2f9; color: #667085; border: 0; border-radius: 7px; padding: 3px 6px; font-family: 'Segoe UI Variable'; font-size: 9px; }
QWidget#desktopStatusPanel { background: transparent; }
QFrame#desktopStatusShell { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffffff,stop:0.65 #f5f8fe,stop:1 #eef3fb); border: 1px solid #bfd0e9; border-radius: 14px; }
QLabel#desktopStatusValue { color: #172744; font-family: "Segoe UI Variable"; font-size: 22px; font-weight: 700; }
QLabel#desktopStatusQuota { color: #55719e; background: #edf3fc; border: 1px solid #d1deef; border-radius: 7px; padding: 7px 8px; }
QPushButton#desktopStatusButton { background: #eef4ff; color: #28569e; border: 1px solid #c9d9f1; border-radius: 6px; padding: 4px 8px; font-size: 10px; }
QPushButton#desktopStatusButton:hover { background: #dceaff; border-color: #75a1e4; }
QLabel#diagnosticText { color: #526071; background: #f8fafc; border: 1px solid #dfe5ee; border-radius: 8px; padding: 10px; line-height: 1.4; }
QPushButton#iconButton, QToolButton#iconButton { background: #ffffff; color: #667085; border: 1px solid #d7dfeb; border-radius: 7px; padding: 6px; }
QPushButton#iconButton:hover, QToolButton#iconButton:hover { background: #edf2f9; color: #26344b; }
QPushButton#primaryButton { background: #326ad6; color: #ffffff; border: 0; border-radius: 7px; padding: 7px 13px; font-weight: 600; }
QPushButton#primaryButton:hover { background: #285bbd; }
QProgressBar { background: #e7ecf3; border: 0; border-radius: 4px; text-align: right; color: #667085; }
QProgressBar::chunk { background: #4e82e3; border-radius: 4px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #c3cedd; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox, QLineEdit { background: #ffffff; color: #26344b; border: 1px solid #d7dfeb; border-radius: 8px; padding: 7px 10px; min-height: 20px; }
QComboBox { padding-right: 36px; }
QComboBox:hover { border-color: #b7c8df; background: #fbfdff; }
QComboBox:focus, QComboBox:on { border-color: #5e91f4; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 32px; border: 0; border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: transparent; }
QComboBox::drop-down:hover { background: #edf3fb; }
QComboBox::down-arrow { image: url(resources/icons/chevron-down.svg); width: 12px; height: 8px; }
QListView#comboPopup { background: #ffffff; color: #26344b; border: 1px solid #cbd7e7; border-radius: 10px; padding: 5px; outline: 0; }
QListView#comboPopup::item { border: 0; border-radius: 6px; padding: 6px 10px; }
QListView#comboPopup::item:hover { background: #edf3fb; }
QListView#comboPopup::item:selected { background: #dbe8ff; color: #1d54b1; }
QPushButton#shortcutRecorder { background: #ffffff; color: #26344b; border: 1px solid #d7dfeb; border-radius: 8px; padding: 7px 12px; text-align: left; }
QPushButton#shortcutRecorder:hover, QPushButton#shortcutRecorder:focus { border-color: #5e91f4; background: #fbfdff; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab { background: transparent; color: #667085; padding: 7px 12px; }
QTabBar::tab:selected { color: #1d54b1; border-bottom: 2px solid #326ad6; }
QCheckBox { color: #526071; }
QMenu { background: #ffffff; color: #26344b; border: 1px solid #d7dfeb; }
QMenu::item { padding: 7px 18px; }
QMenu::item:selected { background: #dbe8ff; }
"""


class ThemeManager:
    def __init__(self):
        self.theme = "dark"
        self.listeners: list[Callable] = []

    def get_theme(self) -> str:
        return self.theme

    def set_theme(self, theme: str):
        if theme in ("auto", "light", "dark"):
            self.theme = theme
            self._notify_listeners()

    def get_stylesheet(self) -> str:
        return DARK_THEME if self.get_effective_theme() == "dark" else LIGHT_THEME

    def get_effective_theme(self) -> str:
        return self._detect_system_theme() if self.theme == "auto" else self.theme

    def apply_theme(self, app):
        palette = QPalette()
        if self.get_effective_theme() == "dark":
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

    def add_listener(self, callback: Callable):
        self.listeners.append(callback)

    def _notify_listeners(self):
        for listener in self.listeners:
            listener()
