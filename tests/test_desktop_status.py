import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor
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
    assert panel.width() == round(270 * 1.18)

    panel.set_theme("dark")
    panel.set_style("mini")
    panel.set_display_size("small")
    assert panel._theme == "dark"
    assert panel.width() == round(285 * 0.86)
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
    assert spy.wait(panel._CLICK_DELAY_MS + 300)
    assert panel._display_mode == "used"
    assert panel._arc(50) == (270 * 16, -180 * 16)
    assert spy.count() == 1
    QTest.qWait(QApplication.doubleClickInterval())

    main_spy = QSignalSpy(panel.show_main)
    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=QPoint(panel.width() // 2, 18))
    assert main_spy.wait(panel._CLICK_DELAY_MS + 300)
    assert main_spy.count() == 1
    QTest.qWait(QApplication.doubleClickInterval())

    minimize_spy = QSignalSpy(panel.minimize_main)
    QTest.mouseDClick(panel, Qt.MouseButton.LeftButton, pos=QPoint(panel.width() // 2, 18))
    QTest.qWait(panel._CLICK_DELAY_MS + 30)
    assert minimize_spy.count() == 1
    assert main_spy.count() == 1


def test_desktop_status_additional_styles_have_distinct_geometry():
    app = QApplication.instance() or QApplication([])
    panel = DesktopStatusPanel()
    panel.set_style("capsule")
    assert panel.size().width() == 320
    assert panel.size().height() == 120
    panel.set_style("tracks")
    assert panel.size().width() == 280
    assert panel.size().height() == 170
    panel.set_display_mode("remaining")
    assert panel._arc(50) == (270 * 16, 180 * 16)
    assert app is not None


def test_dual_ring_order_is_outer_7d_and_inner_5h():
    panel = DesktopStatusPanel()
    panel._q5 = QuotaInfo(used_pct=25, remaining_pct=75)
    panel._q7 = QuotaInfo(used_pct=40, remaining_pct=60)
    bounds = QRectF(0, 0, 180, 180)
    purple = QColor("#705cf2")
    blue = QColor("#3188e8")
    rings = panel._ring_layout(bounds, purple, blue)
    assert [item[3] for item in rings] == ["7D", "5H"]
    assert rings[0][0].width() > rings[1][0].width()
    assert rings[0][2] == purple
    assert rings[1][2] == blue


def test_finalized_style_geometries_match_card_architectures():
    panel = DesktopStatusPanel()
    assert panel._BASE_GEOMETRY == {
        "orb": (280, 230),
        "halo": (270, 280),
        "mini": (285, 200),
        "capsule": (320, 120),
        "tracks": (280, 170),
    }


def test_all_finalized_styles_render_dual_and_single_quota_in_both_themes():
    app = QApplication.instance() or QApplication([])
    panel = DesktopStatusPanel()
    states = (
        UsageSnapshot(
            quota_5h=QuotaInfo(used_pct=32, remaining_pct=68),
            quota_7d=QuotaInfo(used_pct=46, remaining_pct=54),
        ),
        UsageSnapshot(quota_7d=QuotaInfo(used_pct=46, remaining_pct=54)),
    )
    for theme in ("light", "dark"):
        panel.set_theme(theme)
        for style in panel._BASE_GEOMETRY:
            panel.set_style(style)
            for snapshot in states:
                panel.update_snapshot("codex", snapshot)
                panel.show()
                app.processEvents()
                image = panel.grab().toImage()
                assert not image.isNull()
                assert image.width() == panel.width()
                assert image.height() == panel.height()
    panel.hide()


def test_mode_toggle_hit_regions_follow_each_finalized_layout():
    panel = DesktopStatusPanel()
    panel._q5 = QuotaInfo(used_pct=32, remaining_pct=68)
    panel._q7 = QuotaInfo(used_pct=46, remaining_pct=54)
    expected = {
        "orb": (QPoint(92, 106), QPoint(240, 106)),
        "halo": (QPoint(135, 109), QPoint(135, 250)),
        "mini": (QPoint(86, 100), QPoint(230, 100)),
        "capsule": (QPoint(60, 60), QPoint(250, 60)),
        "tracks": (QPoint(190, 85), QPoint(55, 85)),
    }
    for style, (inside, outside) in expected.items():
        panel.set_style(style)
        assert panel._mode_hit_test(inside)
        assert not panel._mode_hit_test(outside)
