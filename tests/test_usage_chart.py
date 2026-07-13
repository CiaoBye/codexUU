from datetime import datetime, timedelta

from app.data.models import DailyToken
from app.ui.usage_chart import aggregate_points
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
