from calendar import monthrange
from datetime import datetime, timedelta

from PySide6.QtWidgets import QApplication

from app.data.models import DailyToken, ModelUsage, RuntimeScope, TokenBreakdown
from app.ui.heatmap import TokenHeatmap
from app.ui.usage_chart import UsagePlot, UsageTrendWidget, aggregate_points, model_period_label, period_range_text
from app.utils.statistics_timezone import configure_statistics_timezone, get_statistics_timezone


def test_daily_points_fill_missing_calendar_days():
    configure_statistics_timezone("fixed", "Asia/Shanghai")
    today = get_statistics_timezone().now_date()
    points = aggregate_points([
        DailyToken(date=datetime.combine(today, datetime.min.time()), total=10),
        DailyToken(date=datetime.combine(today - timedelta(days=2), datetime.min.time()), total=5),
    ], "daily")
    assert len(points) == 30
    assert points[-1][1] == 10
    assert points[-2][1] == 0
    assert points[-3][1] == 5
    configure_statistics_timezone("system")


def test_cumulative_points_finish_at_index_total():
    today = get_statistics_timezone().now_date()
    points = aggregate_points([
        DailyToken(date=datetime.combine(today, datetime.min.time()), total=10),
    ], "cumulative", cumulative_total=100)
    assert points[-1][1] == 100


def test_model_period_counts_and_tokens_follow_selected_mode():
    app = QApplication.instance() or QApplication([])
    today = get_statistics_timezone().now_date()
    now = datetime.combine(today, datetime.min.time())
    old = now - timedelta(days=2)
    model = ModelUsage(
        name="gpt-5",
        runtime=RuntimeScope.CODEX,
        token_total=150,
        tokens=TokenBreakdown(uncached_input=100, cached_input=30, output=20),
        session_count=2,
        turn_count=2,
        daily_tokens=[
            DailyToken(date=now, total=100, uncached_input=70, cached_input=20, output=10),
            DailyToken(date=old, total=50, uncached_input=30, cached_input=10, output=10),
        ],
        session_activity={"new": now, "old": old},
        turn_activity={"new": now, "old": old},
    )
    widget = UsageTrendWidget()
    assert not hasattr(widget, "model_detail_provider")
    widget.mode = "daily"
    period, _points = widget._period_model(model)
    assert period.token_total == 100
    assert period.session_count == 1
    assert period.turn_count == 1
    assert model_period_label("daily", False, today) == f"本日 {today:%m/%d}"
    assert model_period_label("weekly", False, today).startswith("本周 ")
    widget.mode = "cumulative"
    period, _points = widget._period_model(model)
    assert period.token_total == 150
    assert period.session_count == 2
    widget.deleteLater()
    app.processEvents()


def test_scheme_b_range_strip_uses_plain_dates_and_consistent_update_time():
    app = QApplication.instance() or QApplication([])
    today = get_statistics_timezone().now_date()
    widget = UsageTrendWidget()
    assert widget.mode_buttons["daily"].text() == "每日"
    assert widget.mode_buttons["weekly"].text() == "每周"
    assert widget.range_caption.text() == "统计范围"
    assert widget.range_value.text() == f"{today:%m/%d}"
    assert widget.updated_label.text().startswith("数据更新 ")
    assert not hasattr(widget, "summary")

    widget.set_mode("weekly")
    assert widget.range_value.text() == period_range_text("weekly", False, today)
    assert "本周" not in widget.range_value.text()
    widget.set_mode("monthly")
    assert widget.range_value.text() == f"{today:%m}/01-{today:%m}/{monthrange(today.year, today.month)[1]:02d}"
    widget.set_mode("cumulative")
    assert widget.range_value.text() == "全部记录"
    widget.deleteLater()
    app.processEvents()


def test_scheme_b_all_period_and_view_combinations_fit_without_control_overlap():
    app = QApplication.instance() or QApplication([])
    widget = UsageTrendWidget()
    widget.resize(1080, 330)
    widget.show()
    app.processEvents()
    assert widget.height() == 330
    assert widget.content_stack.geometry().bottom() <= widget.rect().bottom()

    for view_index in (0, 1):
        widget._set_view(view_index)
        assert widget.content_stack.currentIndex() == view_index
        for mode in ("daily", "weekly", "monthly", "cumulative"):
            widget.set_mode(mode)
            app.processEvents()
            assert "\n" not in widget.mode_buttons[mode].text()
            assert widget.range_value.text() == period_range_text(mode, False)
            assert widget.range_strip.geometry().bottom() < widget.content_stack.geometry().top()

    widget.hide()
    widget.deleteLater()
    app.processEvents()


def test_usage_plots_reserve_zero_baseline_and_month_labels():
    app = QApplication.instance() or QApplication([])
    today = get_statistics_timezone().now_date()
    monthly = aggregate_points([
        DailyToken(date=datetime.combine(today, datetime.min.time()), total=10),
    ], "monthly")
    assert len(monthly) == 12
    assert monthly[-1][0] == f"{today.month:02d}月"

    plot = UsagePlot()
    plot.resize(520, 210)
    plot.set_points(monthly)
    plot.show()
    app.processEvents()
    plot.grab()
    assert plot._last_plot_rect.bottom() <= plot.height() - plot.BOTTOM_MARGIN
    assert plot._last_plot_rect.bottom() + 24 < plot.height()
    assert all(plot.rect().contains(rect.toAlignedRect()) for rect in plot._last_axis_label_rects)
    assert len(plot._last_x_axis_label_rects) == 12
    assert all(rect.top() >= plot._last_plot_rect.bottom() + 7 for rect in plot._last_x_axis_label_rects)
    plot.hide()


def test_short_model_plot_keeps_labels_inside_without_y_axis_collisions():
    app = QApplication.instance() or QApplication([])
    today = get_statistics_timezone().now_date()
    points = aggregate_points([
        DailyToken(date=datetime.combine(today, datetime.min.time()), total=10),
    ], "monthly")
    plot = UsagePlot()
    plot.resize(480, 62)
    plot.set_points(points)
    plot.show()
    app.processEvents()
    plot.grab()
    assert len(plot._last_x_axis_label_rects) == 12
    assert all(plot.rect().contains(rect.toAlignedRect()) for rect in plot._last_axis_label_rects)
    ordered_y = sorted(plot._last_y_axis_label_rects, key=lambda rect: rect.top())
    assert all(first.bottom() <= second.top() for first, second in zip(ordered_y, ordered_y[1:]))
    plot.hide()


def test_heatmap_expands_grid_and_keeps_only_small_bottom_margin():
    app = QApplication.instance() or QApplication([])
    heatmap = TokenHeatmap()
    heatmap.resize(520, 190)
    heatmap.show()
    app.processEvents()
    heatmap.grab()
    snapshot = heatmap._layout_snapshot
    assert snapshot["cell_size"] >= 15
    assert snapshot["grid_bottom"] <= snapshot["widget_height"] - 8
    assert snapshot["grid_bottom"] >= snapshot["widget_height"] - 12
    assert heatmap._month_label_rects
    assert all(heatmap.rect().contains(rect.toAlignedRect()) for rect in heatmap._month_label_rects)
    assert heatmap._month_label_rects[-1].right() <= heatmap.width()
    heatmap.hide()
