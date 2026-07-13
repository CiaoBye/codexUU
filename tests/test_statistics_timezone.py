from datetime import datetime, timezone

from app.utils.statistics_timezone import configure_statistics_timezone


def test_fixed_timezone_changes_statistics_day():
    value = datetime(2026, 7, 13, 23, 30, tzinfo=timezone.utc)
    configure_statistics_timezone("utc")
    assert configure_statistics_timezone("utc").date_for(value).isoformat() == "2026-07-13"
    assert configure_statistics_timezone("fixed", "Asia/Shanghai").date_for(value).isoformat() == "2026-07-14"
    configure_statistics_timezone("system")
