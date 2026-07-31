import os
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.data.models import QuotaInfo
from app.tray_manager import TrayManager
from app.utils.statistics_timezone import configure_statistics_timezone


def test_tray_monthly_reset_uses_selected_statistics_timezone():
    app = QApplication.instance() or QApplication([])
    configure_statistics_timezone("fixed", "Asia/Shanghai")
    quota = QuotaInfo(
        used_pct=35,
        remaining_pct=65,
        reset_time=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
    )

    assert TrayManager._format_local_reset(quota) == "08/01 08:00"
    configure_statistics_timezone("system")
    assert app is not None
