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
