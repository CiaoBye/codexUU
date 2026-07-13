from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QFrame, QPushButton, QGridLayout, QSizePolicy, QProgressBar,
)

from app.data.models import (
    MultiRuntimeUsageSnapshot, RuntimeScope,
    format_tokens, format_duration, estimate_api_value,
    FULL_MONTHLY_VALUE, CODEX_PROMPT_PRICES, MILLION,
)
from app.ui.progress_ring import DualQuotaRing
from app.ui.task_board import TaskBoardWidget
from app.ui.usage_chart import UsageTrendWidget
from app.ui.project_ranking import ProjectRankingWidget
from app.ui.heatmap import HeatmapWidget
from app.data.codex_reader import read_codex_snapshot
from app.data.claude_reader import read_claude_snapshot
from datetime import datetime, timezone

FONT = "Microsoft YaHei"

CARD_STYLE = "background: rgba(255,255,255,0.06); border-radius: 14px; padding: 14px;"


class TokenBreakdownInline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

    def update_data(self, tokens):
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if tokens is None:
            return
        items = [
            ("\u672a\u7f13\u5b58", tokens.uncached_input, "#60a5fa"),
            ("\u7f13\u5b58", tokens.cached_input, "#a78bfa"),
            ("\u8f93\u51fa", tokens.output, "#f97316"),
        ]
        for name, val, color in items:
            row = QHBoxLayout()
            row.setSpacing(4)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
            row.addWidget(dot)
            n = QLabel(name)
            n.setFont(QFont(FONT, 9))
            n.setStyleSheet("color: #bbb;")
            row.addWidget(n)
            row.addStretch()
            v = QLabel(format_tokens(val))
            v.setFont(QFont(FONT, 9, QFont.Weight.Bold))
            v.setStyleSheet("color: #e0e0e0;")
            row.addWidget(v)
            container = QWidget()
            container.setLayout(row)
            self.layout().addWidget(container)


class StatCard(QFrame):
    def __init__(self, icon_text, title, value="0", dollar="$0", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(CARD_STYLE)
        self.setMinimumHeight(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        icon = QLabel(icon_text)
        icon.setFont(QFont(FONT, 14))
        icon.setStyleSheet("color: #888;")
        header.addWidget(icon)
        t = QLabel(title)
        t.setFont(QFont(FONT, 11))
        t.setStyleSheet("color: #bbb;")
        header.addWidget(t)
        header.addStretch()
        self.dollar_label = QLabel(dollar)
        self.dollar_label.setFont(QFont(FONT, 11))
        self.dollar_label.setStyleSheet("color: #888;")
        header.addWidget(self.dollar_label)
        layout.addLayout(header)

        self.value_label = QLabel(value)
        self.value_label.setFont(QFont(FONT, 28, QFont.Weight.Bold))
        self.value_label.setStyleSheet("color: #ffffff;")
        layout.addWidget(self.value_label)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.08); border-radius: 3px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #60a5fa, stop:1 #a78bfa); border-radius: 3px; }"
        )
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.breakdown = TokenBreakdownInline()
        layout.addWidget(self.breakdown)

    def update_value(self, tokens, dollar="$0"):
        total = tokens.total if tokens else 0
        self.value_label.setText(format_tokens(total))
        self.dollar_label.setText(dollar)
        pct = min(100, int(total / 100_000)) if total > 0 else 0
        self.progress.setValue(pct)
        self.breakdown.update_data(tokens)


class ApiValueBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(CARD_STYLE)
        self.setFixedHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        icon = QLabel("\u2248")
        icon.setFont(QFont(FONT, 14))
        icon.setStyleSheet("color: #60a5fa;")
        header.addWidget(icon)
        t = QLabel("\u7f8a\u6bdb\u8fdb\u5ea6")
        t.setFont(QFont(FONT, 11, QFont.Weight.Bold))
        t.setStyleSheet("color: #e0e0e0;")
        header.addWidget(t)
        header.addStretch()
        self.value_label = QLabel("$0 / $46.5K")
        self.value_label.setFont(QFont(FONT, 13, QFont.Weight.Bold))
        self.value_label.setStyleSheet("color: #ffffff;")
        header.addWidget(self.value_label)
        layout.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.08); border-radius: 4px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #60a5fa, stop:0.5 #a78bfa, stop:1 #f97316); border-radius: 4px; }"
        )
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        markers = QHBoxLayout()
        markers.setSpacing(12)
        for label, color in [("Plus", "#60a5fa"), ("Pro100", "#a78bfa"), ("Pro200", "#f97316")]:
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
            markers.addWidget(dot)
            ml = QLabel(label)
            ml.setFont(QFont(FONT, 8))
            ml.setStyleSheet("color: #888;")
            markers.addWidget(ml)
        markers.addStretch()
        full_label = QLabel("\u6ee1\u989d $46.5K")
        full_label.setFont(QFont(FONT, 8))
        full_label.setStyleSheet("color: #666;")
        markers.addWidget(full_label)
        layout.addLayout(markers)

    def update_value(self, value):
        self.value_label.setText(f"${value:,.0f} / $46.5K")
        pct = min(100, int(value / FULL_MONTHLY_VALUE * 100))
        self.progress.setValue(pct)


class DashboardWidget(QWidget):
    open_settings = Signal()

    def __init__(self, parent=None, translation_manager=None):
        super().__init__(parent)
        self.translation_manager = translation_manager
        self.current_scope = RuntimeScope.CODEX
        self.data = MultiRuntimeUsageSnapshot()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        logo = QLabel("\u2601")
        logo.setFont(QFont(FONT, 18))
        logo.setStyleSheet("color: #60a5fa;")
        top_bar.addWidget(logo)
        title = QLabel(self.translation_manager.tr("codex") if self.translation_manager else "codexU")
        title.setFont(QFont(FONT, 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        top_bar.addWidget(title)
        top_bar.addStretch()

        self.codex_btn = QPushButton(self.translation_manager.tr("codex") if self.translation_manager else "Codex")
        self.codex_btn.setCheckable(True)
        self.codex_btn.setChecked(True)
        self.codex_btn.setFixedHeight(30)
        self.codex_btn.setStyleSheet(
            "QPushButton { background: rgba(96,165,250,0.2); color: #60a5fa;"
            "border: 1px solid rgba(96,165,250,0.4); border-radius: 8px;"
            "padding: 0 16px; font-weight: bold; font-size: 11px; }"
            "QPushButton:checked { background: rgba(96,165,250,0.4);"
            "color: #ffffff; border: 1px solid #60a5fa; }"
        )
        self.codex_btn.clicked.connect(lambda: self._switch_runtime(RuntimeScope.CODEX))
        top_bar.addWidget(self.codex_btn)

        self.claude_btn = QPushButton(self.translation_manager.tr("claude_code") if self.translation_manager else "Claude Code")
        self.claude_btn.setCheckable(True)
        self.claude_btn.setFixedHeight(30)
        self.claude_btn.setStyleSheet(
            "QPushButton { background: rgba(167,139,250,0.2); color: #a78bfa;"
            "border: 1px solid rgba(167,139,250,0.4); border-radius: 8px;"
            "padding: 0 16px; font-weight: bold; font-size: 11px; }"
            "QPushButton:checked { background: rgba(167,139,250,0.4);"
            "color: #ffffff; border: 1px solid #a78bfa; }"
        )
        self.claude_btn.clicked.connect(lambda: self._switch_runtime(RuntimeScope.CLAUDE_CODE))
        top_bar.addWidget(self.claude_btn)

        self.settings_btn = QPushButton("\u2699")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.06); color: #aaa;"
            "border: 1px solid #333; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); color: #fff; }"
        )
        self.settings_btn.clicked.connect(self.open_settings.emit)
        top_bar.addWidget(self.settings_btn)

        self.refresh_btn = QPushButton("\u21bb")
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.06); color: #aaa;"
            "border: 1px solid #333; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); color: #fff; }"
        )
        self.refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(self.refresh_btn)
        layout.addLayout(top_bar)

        upper = QHBoxLayout()
        upper.setSpacing(16)

        left_col = QVBoxLayout()
        left_col.setSpacing(8)
        self.quota_ring = DualQuotaRing()
        left_col.addWidget(self.quota_ring, 0, Qt.AlignmentFlag.AlignCenter)
        self.reset_widget = QWidget()
        rw_layout = QVBoxLayout(self.reset_widget)
        rw_layout.setContentsMargins(0, 4, 0, 0)
        rw_layout.setSpacing(2)
        self.reset_5h = QLabel("5h \u91cd\u7f6e  --:--")
        self.reset_5h.setFont(QFont(FONT, 9))
        self.reset_5h.setStyleSheet("color: #888;")
        rw_layout.addWidget(self.reset_5h)
        self.reset_7d = QLabel("7d \u91cd\u7f6e  --/-- --:--")
        self.reset_7d.setFont(QFont(FONT, 9))
        self.reset_7d.setStyleSheet("color: #888;")
        rw_layout.addWidget(self.reset_7d)
        left_col.addWidget(self.reset_widget)
        left_col.addStretch()

        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self.today_card = StatCard("\u2600", "\u4eca\u65e5", "0", "$0")
        self.week_card = StatCard("\u2611", "\u8fd1 7 \u5929", "0", "$0")
        self.cumul_card = StatCard("\u03a3", "\u7d2f\u8ba1", "0", "$0")
        cards_row.addWidget(self.today_card)
        cards_row.addWidget(self.week_card)
        cards_row.addWidget(self.cumul_card)
        right_col.addLayout(cards_row)

        self.api_value_bar = ApiValueBar()
        right_col.addWidget(self.api_value_bar)

        upper.addLayout(left_col, 0)
        upper.addLayout(right_col, 1)
        layout.addLayout(upper)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { background: transparent; border: none; }"
            "QTabBar::tab { background: rgba(255,255,255,0.06); color: #999;"
            "padding: 8px 16px; margin-right: 3px; border-radius: 8px 8px 0 0; font-size: 12px; }"
            "QTabBar::tab:selected { background: rgba(96,165,250,0.25); color: #ffffff; }"
            "QTabBar::tab:hover { background: rgba(255,255,255,0.1); }"
        )

        self.task_tab = TaskBoardWidget()
        self.trend_tab = UsageTrendWidget()
        self.project_tab = ProjectRankingWidget()
        self.heatmap_tab = HeatmapWidget()

        self.tabs.addTab(self.task_tab, self.translation_manager.tr("today_tasks") if self.translation_manager else "\u2630 \u4eca\u65e5\u4efb\u52a1")
        self.tabs.addTab(self.trend_tab, self.translation_manager.tr("usage_trend") if self.translation_manager else "\u2261 \u7528\u91cf\u8d8b\u52bf")
        self.tabs.addTab(self.project_tab, self.translation_manager.tr("project_ranking") if self.translation_manager else "\u673a\u5221\u6392\u884c")
        self.tabs.addTab(self.heatmap_tab, self.translation_manager.tr("skill") if self.translation_manager else "Skill")

        layout.addWidget(self.tabs, 1)
        
        # Connect to translation manager
        if self.translation_manager:
            self.translation_manager.add_listener(self.update_text)

    def _switch_runtime(self, scope):
        self.current_scope = scope
        self.codex_btn.setChecked(scope == RuntimeScope.CODEX)
        self.claude_btn.setChecked(scope == RuntimeScope.CLAUDE_CODE)
        self._update_display()
    
    def update_text(self):
        if not self.translation_manager:
            return
        
        self.codex_btn.setText(self.translation_manager.tr("codex"))
        self.claude_btn.setText(self.translation_manager.tr("claude_code"))
        
        # Update tab names
        self.tabs.setTabText(0, self.translation_manager.tr("today_tasks"))
        self.tabs.setTabText(1, self.translation_manager.tr("usage_trend"))
        self.tabs.setTabText(2, self.translation_manager.tr("project_ranking"))
        self.tabs.setTabText(3, self.translation_manager.tr("skill"))

    def refresh(self):
        self.data.codex = read_codex_snapshot()
        self.data.claude_code = read_claude_snapshot()
        self.data.tasks.clear()
        from app.data.codex_reader import read_task_board as ct
        self.data.tasks.extend(ct())
        from app.data.claude_reader import read_claude_tasks as clt
        self.data.tasks.extend(clt())
        self.data.daily_tokens.clear()
        from app.data.codex_reader import read_daily_tokens
        self.data.daily_tokens = read_daily_tokens()
        self.data.projects.clear()
        from app.data.codex_reader import read_projects as cp
        from app.data.claude_reader import read_claude_projects as clp
        self.data.projects.extend(cp())
        self.data.projects.extend(clp())
        self.data.projects.sort(key=lambda p: p.token_total, reverse=True)
        self._update_display()

    def _update_display(self):
        snap = self.data.for_scope(self.current_scope)
        q5 = snap.quota_5h
        q7 = snap.quota_7d
        self.quota_ring.set_quota(q5.remaining_pct if q5 else 0, q7.remaining_pct if q7 else 0)
        now = datetime.now(timezone.utc)
        r5, r7 = "--:--", "--/-- --:--"
        if q5 and q5.reset_time and q5.reset_time > now:
            r5 = format_duration(q5.reset_time - now)
        if q7 and q7.reset_time and q7.reset_time > now:
            r7 = format_duration(q7.reset_time - now)
        self.reset_5h.setText(f"5h \u91cd\u7f6e  {r5}")
        self.reset_7d.setText(f"7d \u91cd\u7f6e  {r7}")
        today_val = estimate_api_value(snap.tokens.today, CODEX_PROMPT_PRICES)
        week_val = estimate_api_value(snap.tokens.last_7d, CODEX_PROMPT_PRICES)
        cum_val = snap.api_equivalent_value
        self.today_card.update_value(snap.tokens.today, f"${today_val:,.2f}")
        self.week_card.update_value(snap.tokens.last_7d, f"${week_val:,.0f}")
        self.cumul_card.update_value(snap.tokens.cumulative, f"${cum_val:,.0f}")
        self.api_value_bar.update_value(cum_val)
        self.task_tab.update_tasks(self.data.tasks)
        self.trend_tab.set_data(self.data.daily_tokens)
        self.project_tab.update_projects(self.data.projects)
        self.heatmap_tab.set_data(self.data.daily_tokens)
