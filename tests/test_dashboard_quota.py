import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.data.models import (
    DailyToken,
    ProviderBalance,
    ProviderUsageSnapshot,
    QuotaInfo,
    TokenBreakdown,
    TokenStats,
    UsageSnapshot,
)
from app.ui.dashboard import DashboardWidget, ProviderScopeButton, ProviderUsageLabel, QuotaPanel
from app.utils.settings import SettingsManager
from datetime import datetime


def test_quota_compass_center_click_switches_remaining_and_used():
    app = QApplication.instance() or QApplication([])
    panel = QuotaPanel()
    panel.update_quota(QuotaInfo(used_pct=42, remaining_pct=58), QuotaInfo(used_pct=21, remaining_pct=79))
    panel.show()
    app.processEvents()
    spy = QSignalSpy(panel.mode_changed)
    QTest.mouseClick(panel.dial, Qt.MouseButton.LeftButton, pos=panel.dial.rect().center())
    assert panel.display_mode == "used"
    assert spy.count() == 1
    QTest.mouseClick(panel.dial, Qt.MouseButton.LeftButton, pos=panel.dial.rect().center())
    assert panel.display_mode == "remaining"
    assert spy.count() == 2
    panel.hide()


def test_quota_scheme_c_uses_adaptive_centered_reset_strip_without_design_badge():
    app = QApplication.instance() or QApplication([])
    panel = QuotaPanel()
    q5 = QuotaInfo(used_pct=42, remaining_pct=58)
    q7 = QuotaInfo(used_pct=21, remaining_pct=79)
    panel.update_quota(q5, q7)
    panel.show()
    app.processEvents()

    assert panel.title.text() == "额度使用情况"
    assert not hasattr(panel, "mode_badge")
    assert not hasattr(panel, "subtitle")
    assert panel.reset_strip.five_section.isVisible()
    assert panel.reset_strip.divider.isVisible()
    assert panel.reset_strip.seven_section.isVisible()

    panel.update_quota(None, q7)
    app.processEvents()
    assert panel.reset_strip.five_section.isHidden()
    assert panel.reset_strip.divider.isHidden()
    assert panel.reset_strip.seven_section.isVisible()

    # The dial and reset strip own distinct vertical regions at the real card
    # height, and the visible single reset section is centered as a group.
    assert panel.dial.geometry().bottom() < panel.reset_strip.geometry().top()
    seven_center = panel.reset_strip.seven_section.mapTo(panel.reset_strip, panel.reset_strip.seven_section.rect().center()).x()
    assert abs(seven_center - panel.reset_strip.rect().center().x()) <= 2
    panel.hide()


def test_quota_panel_explains_exhaustion_without_inventing_missing_windows():
    app = QApplication.instance() or QApplication([])
    panel = QuotaPanel()
    panel.update_quota(None, None, "exhausted")
    panel.show()
    app.processEvents()

    assert panel.quota_status == "exhausted"
    assert panel.dial.quota_status == "exhausted"
    assert panel.reset_strip.five_section.isHidden()
    assert panel.reset_strip.seven_section.isHidden()
    image = panel.dial.grab().toImage()
    assert image.width() > 0 and image.height() > 0
    panel.hide()


def test_quota_panel_shows_monthly_reset_details_without_creating_a_ring():
    app = QApplication.instance() or QApplication([])
    panel = QuotaPanel()
    month = QuotaInfo(used_pct=35, remaining_pct=65, window_minutes=43800)
    panel.update_quota(None, None, "available", month)
    panel.show()
    app.processEvents()

    assert panel.reset_strip.month_section.isVisible()
    assert panel.dial.q5 is None and panel.dial.q7 is None
    assert panel.dial.grab().toImage().width() > 0
    panel.hide()


def test_provider_usage_label_keeps_relay_balance_separate_and_explained():
    app = QApplication.instance() or QApplication([])
    label = ProviderUsageLabel()
    label.set_snapshot(ProviderUsageSnapshot(
        provider_name="WawAPI",
        balance=ProviderBalance(remaining=34.66, unit="USD", plan_name="Pro"),
        tokens=TokenStats(today=TokenBreakdown(uncached_input=80, cached_input=20, output=10)),
        request_count=3,
        success_count=2,
        failure_count=1,
        current_month_cost_usd=1.25,
        data_source="CC Switch test database",
    ))
    assert "WawAPI" in label.text()
    assert "34.66" in label.text()
    assert "CC Switch test database" in label.toolTip()
    assert "5h" not in label.toolTip()
    label.deleteLater()
    app.processEvents()


def _provider_snapshot():
    today = datetime.now()
    token_stats = TokenStats(
        today=TokenBreakdown(uncached_input=80, cached_input=20, output=10),
        current_week=TokenBreakdown(uncached_input=180, cached_input=40, output=20),
        current_month=TokenBreakdown(uncached_input=280, cached_input=60, output=30),
        cumulative=TokenBreakdown(uncached_input=380, cached_input=80, output=40),
    )
    return ProviderUsageSnapshot(
        provider_name="WawAPI",
        balance=ProviderBalance(remaining=34.66, unit="USD", plan_name="Pro"),
        tokens=token_stats,
        daily_tokens=[DailyToken(date=today, total=110, uncached_input=80, cached_input=20, output=10)],
        request_count=3,
        success_count=2,
        failure_count=1,
        today_cost_usd=0.25,
        current_week_cost_usd=0.65,
        current_month_cost_usd=1.25,
        total_cost_usd=2.75,
        data_source="CC Switch test database",
    )


def test_provider_scope_button_uses_station_name_and_balance_tooltip():
    app = QApplication.instance() or QApplication([])
    button = ProviderScopeButton()
    button.set_snapshot(_provider_snapshot())
    assert button.text() == "WawAPI"
    assert button.isEnabled()
    assert "34.66" in button.toolTip()
    button.set_snapshot(None)
    assert button.text() == "\u4e2d\u8f6c"
    assert not button.isEnabled()
    button.deleteLater()
    app.processEvents()


def test_dashboard_provider_scope_uses_provider_data_and_all_restores_codex_data():
    app = QApplication.instance() or QApplication([])
    dashboard = DashboardWidget()
    provider = _provider_snapshot()
    dashboard.data.ccswitch = provider
    dashboard.data.codex = UsageSnapshot(tokens=TokenStats(
        today=TokenBreakdown(uncached_input=900),
        current_week=TokenBreakdown(uncached_input=900),
        current_month=TokenBreakdown(uncached_input=900),
        cumulative=TokenBreakdown(uncached_input=900),
    ))
    dashboard._set_model_scope("provider")
    app.processEvents()
    assert dashboard.provider_scope_button.text() == "WawAPI"
    assert dashboard.current_model_scope == "provider"
    assert dashboard.quota_card.provider_mode
    assert dashboard.quota_card.reset_strip.isHidden()
    assert dashboard.value_card.provider_mode
    assert dashboard.today_card._tokens.total == provider.tokens.today.total

    dashboard._set_model_scope("all")
    app.processEvents()
    assert dashboard.current_model_scope == "all"
    assert not dashboard.quota_card.provider_mode
    assert not dashboard.value_card.provider_mode
    assert dashboard.today_card._tokens.total == 900
    dashboard.deleteLater()
    app.processEvents()


def test_dashboard_model_scope_switch_updates_with_settings_manager(tmp_path):
    app = QApplication.instance() or QApplication([])
    manager = SettingsManager(tmp_path / "config.json")
    manager.set_model_scope("provider")
    dashboard = DashboardWidget(settings_manager=manager)
    dashboard.data.ccswitch = _provider_snapshot()
    dashboard.data.codex = UsageSnapshot(tokens=TokenStats(
        today=TokenBreakdown(uncached_input=900),
        current_week=TokenBreakdown(uncached_input=900),
        current_month=TokenBreakdown(uncached_input=900),
        cumulative=TokenBreakdown(uncached_input=900),
    ))

    dashboard._update()
    assert dashboard.quota_card.provider_mode
    dashboard._set_model_scope("gpt")
    app.processEvents()
    assert dashboard.current_model_scope == "gpt"
    assert dashboard.model_scope_buttons["gpt"].isChecked()
    assert not dashboard.quota_card.provider_mode
    dashboard.deleteLater()
    app.processEvents()


def test_single_seven_day_ring_has_prominent_purple_track():
    app = QApplication.instance() or QApplication([])
    panel = QuotaPanel()
    panel.update_quota(None, QuotaInfo(used_pct=22, remaining_pct=78))
    panel.show()
    app.processEvents()
    ring = panel.dial.single_ring_rect
    assert ring.width() >= 110
    image = panel.dial.grab().toImage()
    purple_pixels = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.blue() > 150 and color.blue() > color.red() + 35 and color.red() > 50:
                purple_pixels += 1
    assert purple_pixels >= 80
    panel.hide()
