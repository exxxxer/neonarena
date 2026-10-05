"""Neon Arena entry point: python main.py."""

import logging
import sys

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from neonarena.storage import Repository, data_dir
from neonarena.theme import STYLE
from neonarena.windows import GameWindow, MenuWindow, SettingsDialog, UpgradeDialog


def main():
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("NeonArena")
    QCoreApplication.setApplicationName("NeonArena")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    logging.basicConfig(
        filename=data_dir() / "neon-arena.log",
        level=logging.ERROR,
        format="%(asctime)s %(message)s",
        encoding="utf-8",
    )

    def error_hook(error_type, error, traceback):
        logging.error("Application error", exc_info=(error_type, error, traceback))
        QMessageBox.critical(QApplication.activeWindow(), "Ошибка Neon Arena", str(error))

    sys.excepthook = error_hook
    repository = Repository(data_dir() / "neon-arena.sqlite3")
    window = MenuWindow(repository)
    window.show()
    if "--smoke-test" in sys.argv:
        try:
            player = repository.players()[0]
            game = GameWindow(repository, player["id"], "Нормально")
            game.timer.stop()
            game.show()
            settings = SettingsDialog(repository)
            settings.show()
            game.world.state = "upgrade"
            game.world.upgrade_choices = ["damage", "heal", "speed"]
            upgrade = UpgradeDialog(game.world)
            upgrade.show()
            QTimer.singleShot(1000, lambda: app.exit(0))
        except Exception:
            logging.exception("Packaged smoke test failed")
            repository.close()
            return 1
    result = app.exec()
    repository.close()
    return result


if __name__ == "__main__":
    sys.exit(main())
