from datetime import datetime, timedelta

from PySide6.QtWidgets import QApplication

from app.data.models import DailyToken, ModelUsage, RuntimeScope, TokenBreakdown
from app.ui.usage_chart import UsageTrendWidget, aggregate_points
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
    old = now - timedelta(days=45)
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
    widget.mode = "daily"
    period, _points = widget._period_model(model)
    assert period.token_total == 100
    assert period.session_count == 1
    assert period.turn_count == 1
    widget.mode = "cumulative"
    period, _points = widget._period_model(model)
    assert period.token_total == 150
    assert period.session_count == 2
    widget.deleteLater()
    app.processEvents()
