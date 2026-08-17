import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from app.main_window import MainAppWindow


def test_main_window_uses_design_size_as_hard_minimum():
    app = QApplication.instance() or QApplication([])
    window = MainAppWindow()
    assert window.minimumSize() == QSize(1060, 720)
    assert window.size() == QSize(1060, 720)
    window.resize(1060, 720)
    assert window.width() >= 1060
    assert window.height() >= 720
    window.deleteLater()
    app.processEvents()


def test_normal_window_size_is_constrained_to_design_aspect():
    assert MainAppWindow.constrained_client_size(980, 680, "width") == QSize(1060, 720)
    assert MainAppWindow.constrained_client_size(1325, 850, "width") == QSize(1325, 900)
    assert MainAppWindow.constrained_client_size(1250, 900, "height") == QSize(1325, 900)


def test_native_minimum_size_scales_the_logical_client_for_dpi():
    assert MainAppWindow.logical_to_native(1060, 96) == 1060
    assert MainAppWindow.logical_to_native(1060, 144) == 1590
    assert MainAppWindow.native_minimum_outer_size(144, (8, 36, 8, 8)) == (1606, 1124)


def test_native_sizing_keeps_the_fixed_edge_and_design_ratio():
    aspect = 1500 / 1000

    right_edge = MainAppWindow.constrained_outer_rect(
        100, 200, 1600, 900, MainAppWindow.WMSZ_RIGHT, aspect, 1100, 800
    )
    assert right_edge == (100, 200, 1600, 1200)

    top_edge = MainAppWindow.constrained_outer_rect(
        100, 200, 1300, 1400, MainAppWindow.WMSZ_TOP, aspect, 1100, 800
    )
    assert top_edge == (100, 200, 1900, 1400)

    corner = MainAppWindow.constrained_outer_rect(
        100, 200, 1900, 1300, MainAppWindow.WMSZ_BOTTOMRIGHT,
        aspect, 1100, 800, start_width=1500, start_height=1000
    )
    assert corner == (100, 200, 1900, 1400)


def test_native_sizing_preserves_client_ratio_with_frame_margins():
    result = MainAppWindow.constrained_outer_rect(
        100, 200, 1600, 900, MainAppWindow.WMSZ_RIGHT,
        MainAppWindow.DESIGN_ASPECT, 1076, 759,
        frame_width=16, frame_height=39,
    )
    assert result == (100, 200, 1600, 1247)
    client_width = result[2] - result[0] - 16
    client_height = result[3] - result[1] - 39
    assert abs(client_width / client_height - MainAppWindow.DESIGN_ASPECT) < 0.002


def test_native_sizing_clamps_minimum_without_moving_the_opposite_edge():
    result = MainAppWindow.constrained_outer_rect(
        100, 200, 1200, 1000, MainAppWindow.WMSZ_LEFT, 1.5, 1100, 800
    )
    assert result == (0, 200, 1200, 1000)


def test_all_dashboard_tabs_fit_the_standard_client_canvas():
    app = QApplication.instance() or QApplication([])
    window = MainAppWindow()
    window.show()
    app.processEvents()
    assert window.size() == QSize(1060, 720)
    assert window.dashboard.geometry().size() == window.centralWidget().contentsRect().size()
    for index in range(window.dashboard.stack.count()):
        window.dashboard.stack.setCurrentIndex(index)
        app.processEvents()
        current = window.dashboard.stack.currentWidget()
        assert current.geometry().bottom() <= window.dashboard.stack.contentsRect().bottom()
        assert current.geometry().right() <= window.dashboard.stack.contentsRect().right()
    window.hide()
    window.deleteLater()
    app.processEvents()


def test_all_dashboard_tabs_fit_an_enlarged_client_canvas():
    app = QApplication.instance() or QApplication([])
    window = MainAppWindow()
    window.show()
    app.processEvents()
    window.resize_normal_client(1325, 850, "width")
    app.processEvents()

    assert window.size() == QSize(1325, 900)
    for index in range(window.dashboard.stack.count()):
        window.dashboard.stack.setCurrentIndex(index)
        app.processEvents()
        current = window.dashboard.stack.currentWidget()
        assert current.geometry().bottom() <= window.dashboard.stack.contentsRect().bottom()
        assert current.geometry().right() <= window.dashboard.stack.contentsRect().right()
    window.hide()
    window.deleteLater()
    app.processEvents()
