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
    assert panel.width() == round(250 * 1.18)

    panel.set_theme("dark")
    panel.set_style("mini")
    panel.set_display_size("small")
    assert panel._theme == "dark"
    assert panel.width() == round(250 * 0.20)
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
    assert panel.size().width() == 330
    assert panel.size().height() == 150
    panel.set_style("tracks")
    assert panel.size().width() == 330
    assert panel.size().height() == 150
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
        "orb": (250, 250),
        "halo": (250, 250),
        "mini": (250, 250),
        "capsule": (330, 150),
        "tracks": (330, 150),
    }


def test_new_forms_keep_comparable_medium_size_footprints():
    panel = DesktopStatusPanel()
    sizes = list(panel._BASE_GEOMETRY.values())
    areas = [width * height for width, height in sizes]
    assert panel._BASE_GEOMETRY["orb"] == panel._BASE_GEOMETRY["halo"] == panel._BASE_GEOMETRY["mini"]
    assert max(areas) / min(areas) <= 1.3


def test_small_preset_uses_strict_uniform_canvas_scaling():
    panel = DesktopStatusPanel()
    panel.set_display_size("small")
    font = panel._scaled_font("Segoe UI Variable", 8)
    scale_x, scale_y = panel._layout_scales()
    assert font.pixelSize() * min(scale_x, scale_y) >= 1


def test_desktop_status_supports_continuous_scale_without_breaking_canvas_mapping():
    app = QApplication.instance() or QApplication([])
    panel = DesktopStatusPanel()
    snapshot = UsageSnapshot(quota_7d=QuotaInfo(used_pct=46, remaining_pct=54))
    for style in panel._BASE_GEOMETRY:
        panel.set_style(style)
        for scale in (0.20, 0.63, 1.37, 3.0):
            panel.set_display_scale(scale)
            panel.update_snapshot("codex", snapshot)
            panel.show()
            app.processEvents()
            image = panel.grab().toImage()
            assert not image.isNull()
            assert image.size() == panel.size()
    panel.set_style("orb")
    panel.set_display_scale(0.63)
    assert panel.width() == round(250 * 0.63)
    assert panel._size == "custom"
    panel.set_display_scale(9)
    assert panel.width() == round(250 * 3.0)
    panel.hide()


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
            for size in ("small", "medium", "large"):
                panel.set_display_size(size)
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
        "orb": (QPoint(125, 125), QPoint(15, 15)),
        "halo": (QPoint(125, 125), QPoint(15, 15)),
        "mini": (QPoint(125, 125), QPoint(15, 15)),
        "capsule": (QPoint(165, 80), QPoint(40, 80)),
        "tracks": (QPoint(155, 100), QPoint(10, 100)),
    }
    for style, (inside, outside) in expected.items():
        panel.set_style(style)
        assert panel._mode_hit_test(inside)
        assert not panel._mode_hit_test(outside)


def test_all_size_presets_keep_layout_hit_regions_in_sync():
    """The visual canvas and mouse regions must use the same size transform."""
    panel = DesktopStatusPanel()
    panel._q5 = QuotaInfo(used_pct=32, remaining_pct=68)
    panel._q7 = QuotaInfo(used_pct=46, remaining_pct=54)
    base_points = {
        "orb": (QPoint(125, 125), QPoint(15, 15)),
        "halo": (QPoint(125, 125), QPoint(15, 15)),
        "mini": (QPoint(125, 125), QPoint(15, 15)),
        "capsule": (QPoint(165, 80), QPoint(40, 80)),
        "tracks": (QPoint(155, 100), QPoint(10, 100)),
    }
    for style, (inside, outside) in base_points.items():
        panel.set_style(style)
        base_width, base_height = panel._BASE_GEOMETRY[style]
        for size in ("small", "medium", "large"):
            panel.set_display_size(size)
            scale_x = panel.width() / base_width
            scale_y = panel.height() / base_height
            scale_point = lambda point: QPoint(
                round(point.x() * scale_x), round(point.y() * scale_y),
            )
            assert panel._mode_hit_test(scale_point(inside))
            assert not panel._mode_hit_test(scale_point(outside))
