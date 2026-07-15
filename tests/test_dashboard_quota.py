import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.data.models import QuotaInfo
from app.ui.dashboard import QuotaPanel


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
