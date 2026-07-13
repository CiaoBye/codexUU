from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.main_window import MainAppWindow
from app.tray_manager import TrayManager
from app.settings_dialog import SettingsDialog
from app.utils.settings import SettingsManager
from app.utils.translation import TranslationManager
from app.utils.theme import ThemeManager


class CodexUApplication:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("codexU")
        self.app.setOrganizationName("codexU")
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyle("Fusion")
        self.app.setFont(QFont("Microsoft YaHei", 9))
        
        # Initialize managers
        config_path = Path.home() / ".codexU" / "config.json"
        self.settings_manager = SettingsManager(config_path)
        self.settings_manager.load()
        
        self.translation_manager = TranslationManager()
        self.translation_manager.set_language(self.settings_manager.get_language())
        
        self.theme_manager = ThemeManager()
        self.theme_manager.set_theme(self.settings_manager.get_theme())
        self.theme_manager.apply_theme(self.app)
        
        self.settings_dialog = None
        self.window = MainAppWindow(
            settings_manager=self.settings_manager,
            translation_manager=self.translation_manager,
            theme_manager=self.theme_manager
        )
        self.tray = TrayManager()

        self.tray.show_main_window.connect(self._show_main_window)
        self.tray.show_settings.connect(self._show_settings)
        self.tray.quit_app.connect(self.app.quit)
        self.window.dashboard.open_settings.connect(self._show_settings)

        self.window.show()

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh)
        self.refresh_timer.start(60000)
        QTimer.singleShot(200, self._refresh)

    def _show_main_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _show_settings(self):
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(
                self.window,
                settings_manager=self.settings_manager,
                translation_manager=self.translation_manager,
                theme_manager=self.theme_manager
            )
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _refresh(self):
        try:
            self.window.dashboard.refresh()
            self.tray.update_data(self.window.dashboard.data)
        except Exception as e:
            print(f"[codexU] refresh error: {e}", file=sys.stderr)

    def run(self):
        return self.app.exec()


def main():
    app = CodexUApplication()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
