import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.desktop_status import DesktopStatusPanel


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
