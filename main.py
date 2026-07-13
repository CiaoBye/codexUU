from __future__ import annotations
import sys
import threading
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
from app.utils.statistics_timezone import configure_statistics_timezone
from app.utils.update_checker import check_for_update
from app.constants import APP_NAME, APP_VERSION


class CodexUApplication:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setApplicationVersion(APP_VERSION)
        self.app.setOrganizationName(APP_NAME)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyle("Fusion")
        self.app.setFont(QFont("Microsoft YaHei", 9))

        config_path = Path.home() / ".codexU" / "config.json"
        self.settings_manager = SettingsManager(config_path)
        self.settings_manager.load()
        configure_statistics_timezone(*self.settings_manager.get_statistics_timezone())
        
        self.translation_manager = TranslationManager()
        self.translation_manager.set_language(self.settings_manager.get_language())
        
        self.theme_manager = ThemeManager()
        self.theme_manager.set_theme(self.settings_manager.get_theme())
        self.theme_manager.apply_theme(self.app)

        self.settings_dialog = None
        self.window = MainAppWindow(
            settings_manager=self.settings_manager,
            translation_manager=self.translation_manager,
            theme_manager=self.theme_manager,
        )
        self.tray = TrayManager(self.settings_manager)

        self.tray.show_main_window.connect(self._show_main)
        self.tray.show_settings.connect(self._show_settings)
        self.tray.quit_app.connect(self.app.quit)
        self.window.dashboard.open_settings.connect(self._show_settings)
        self.window.dashboard.data_updated.connect(self.tray.update_data)
        self.tray.status_icon_changed.connect(self.window.setWindowIcon)

        self.window.show()
        QTimer.singleShot(300, self._refresh)
        QTimer.singleShot(1800, self._auto_check_update)

        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(60000)

    def _show_main(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _show_settings(self):
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(
                self.window,
                settings_manager=self.settings_manager,
                translation_manager=self.translation_manager,
                theme_manager=self.theme_manager,
            )
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _refresh(self):
        try:
            self.window.dashboard.refresh(silent=True)
        except Exception:
            pass

    def _auto_check_update(self):
        auto_update, include_beta = self.settings_manager.get_update_preferences()
        if not auto_update:
            return

        def worker():
            release = check_for_update(APP_VERSION, include_beta=include_beta)
            if release:
                QTimer.singleShot(
                    0,
                    lambda: self.tray.tray_icon.showMessage(
                        "CodexUU 有可用更新",
                        f"发现 {release.tag_name}，打开设置查看详情。",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def run(self):
        return self.app.exec()


def main():
    app = CodexUApplication()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
