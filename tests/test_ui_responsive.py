import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea, QTabWidget

from app.main_window import MainAppWindow
from app.settings_dialog import SettingsDialog
from app.utils.settings import SettingsManager
from app.utils.theme import ThemeManager
from app.utils.translation import TranslationManager


def test_main_window_resize_path_is_synchronous_and_interruptible():
    app = QApplication.instance() or QApplication([])
    window = MainAppWindow()

    assert not hasattr(window, "_pending_aspect_size")
    assert not hasattr(window, "_aspect_adjusting")
    assert window._resize_settle_timer.isSingleShot()
    window.resize(1060, 720)
    app.processEvents()
    assert window.size().width() >= window.DESIGN_WIDTH
    assert window.size().height() >= window.DESIGN_HEIGHT
    window.deleteLater()
    app.processEvents()


def test_settings_dialog_uses_scrollable_categories_and_fixed_footer(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(
        settings_manager=SettingsManager(Path(tmp_path) / "config.json"),
        translation_manager=TranslationManager(),
        theme_manager=ThemeManager(),
    )
    dialog.show()
    app.processEvents()

    assert dialog.minimumWidth() >= 740
    assert dialog.tabs.tabPosition() == QTabWidget.TabPosition.North
    scrolls = dialog.findChildren(QScrollArea)
    assert len(scrolls) == 3
    assert all(scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff for scroll in scrolls)
    assert dialog.save_btn.isEnabled() is False

    dialog.theme_combo.setCurrentIndex(1)
    assert dialog.save_btn.isEnabled() is True
    assert dialog.display_note.height() >= dialog.display_note.sizeHint().height()

    dialog._settings_dirty = False
    dialog.close()
    app.processEvents()
