import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from app.desktop_status import DesktopStatusPanel
from app.data.models import QuotaInfo, UsageSnapshot


def test_desktop_status_theme_style_and_size_are_explicit():
    app = QApplication.instance() or QApplication([])
    panel = DesktopStatusPanel()

    panel.set_theme("light")
    panel.set_style("halo")
    panel.set_display_size("large")
    assert panel._theme == "light"
    assert panel._style == "halo"
    assert panel._size == "large"
    assert panel.width() == round(188 * 1.18)

    panel.set_theme("dark")
    panel.set_style("mini")
    panel.set_display_size("small")
    assert panel._theme == "dark"
    assert panel.width() == round(116 * 0.86)
    assert app is not None


def test_desktop_status_supports_dual_quota_and_center_mode_toggle():
    app = QApplication.instance() or QApplication([])
    panel = DesktopStatusPanel()
    panel.set_style("halo")
    panel.set_display_mode("remaining")
    snapshot = UsageSnapshot(
        quota_5h=QuotaInfo(used_pct=25, remaining_pct=75),
        quota_7d=QuotaInfo(used_pct=40, remaining_pct=60),
    )
    panel.update_snapshot("codex", snapshot)
    assert panel._q5 is snapshot.quota_5h
    assert panel._q7 is snapshot.quota_7d
    spy = QSignalSpy(panel.mode_change_requested)
    panel.show()
    app.processEvents()
    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=panel.rect().center())
    assert panel._display_mode == "used"
    assert spy.count() == 1
