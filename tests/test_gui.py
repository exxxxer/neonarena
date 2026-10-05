"""Qt integration: input, Designer forms, navigation and SQLite writeback."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from neonarena.storage import Repository
from neonarena.theme import STYLE
from neonarena.windows import GameWindow, MenuWindow, ResultDialog, SettingsDialog, UpgradeDialog

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
APP.setStyleSheet(STYLE)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "test.sqlite3")
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if isinstance(window, GameWindow):
                window.timer.stop()
                window.finished = True
            window.close()
        APP.processEvents()
        self.repo.close()
        self.temp.cleanup()

    def show(self, window):
        self.windows.append(window)
        window.show()
        window.activateWindow()
        APP.processEvents()
        if isinstance(window, GameWindow):
            window.timer.stop()
            window.world.resume()
            window.canvas.setFocus()
        return window

    def game(self):
        return self.show(GameWindow(self.repo, self.repo.players()[0]["id"], "Нормально"))

    def test_menu_profile_buttons_and_empty_state(self):
        menu = self.show(MenuWindow(self.repo))
        with patch.object(QInputDialog, "getText", return_value=("Новый", True)):
            QTest.mouseClick(menu.addPlayerButton, Qt.MouseButton.LeftButton)
        self.assertEqual(menu.playerCombo.currentText(), "Новый")
        with patch.object(QInputDialog, "getText", return_value=("Новое имя", True)):
            QTest.mouseClick(menu.renamePlayerButton, Qt.MouseButton.LeftButton)
        self.assertEqual(menu.playerCombo.currentText(), "Новое имя")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            menu.delete_player()
            menu.delete_player()
        self.assertFalse(menu.startButton.isEnabled())

    def test_settings_button_persists(self):
        settings = self.show(SettingsDialog(self.repo))
        settings.volumeSlider.setValue(30)
        settings.muteCheck.setChecked(True)
        QTest.mouseClick(settings.saveButton, Qt.MouseButton.LeftButton)
        self.assertEqual(self.repo.setting("volume"), 30)
        self.assertTrue(self.repo.setting("muted"))

    def test_keyboard_movement_release_dash_and_pause(self):
        game = self.game()
        x = game.world.player.x
        QTest.keyPress(game.canvas, Qt.Key.Key_D)
        game.world.update(1 / 120, game.canvas.movement())
        self.assertGreater(game.world.player.x, x)
        QTest.keyRelease(game.canvas, Qt.Key.Key_D)
        self.assertEqual(game.canvas.movement(), (0, 0))
        QTest.keyClick(game.canvas, Qt.Key.Key_Space)
        self.assertGreater(game.world.player.dash_cooldown, 0)
        QTest.keyClick(game.canvas, Qt.Key.Key_Escape)
        self.assertEqual(game.world.state, "paused")
        QTest.keyClick(game.canvas, Qt.Key.Key_Escape)
        self.assertEqual(game.world.state, "playing")

    def test_mouse_aim_fire_and_weapon_switch(self):
        game = self.game()
        point = QPoint(game.canvas.width() * 3 // 4, game.canvas.height() // 2)
        QTest.mousePress(game.canvas, Qt.MouseButton.LeftButton, pos=point)
        game.world.update(1 / 120, aim=game.canvas.aim, firing=game.canvas.firing)
        self.assertGreater(len(game.world.projectiles), 0)
        QTest.mouseRelease(game.canvas, Qt.MouseButton.LeftButton, pos=point)
        self.assertFalse(game.canvas.firing)
        QTest.mouseClick(game.canvas, Qt.MouseButton.RightButton, pos=point)
        self.assertEqual(game.world.player.weapon, "scatter")
        QTest.keyClick(game.canvas, Qt.Key.Key_1)
        self.assertEqual(game.world.player.weapon, "pulse")

    def test_canvas_resize_preserves_coordinate_mapping(self):
        game = self.game()
        game.resize(1450, 950)
        APP.processEvents()
        scale, ox, oy = game.canvas.transform()
        world = game.canvas.world_position(QPointF(ox + 550 * scale, oy + 325 * scale))
        self.assertAlmostEqual(world[0], 550)
        self.assertAlmostEqual(world[1], 325)

    def test_upgrade_choice_starts_next_wave(self):
        game = self.game()
        game.world.state = "upgrade"
        game.world.upgrade_choices = ["damage", "heal", "speed"]

        def choose():
            for widget in APP.topLevelWidgets():
                if isinstance(widget, UpgradeDialog):
                    QTest.mouseClick(widget.upgradeButton0, Qt.MouseButton.LeftButton)

        QTimer.singleShot(30, choose)
        game.select_upgrade()
        game.timer.stop()
        self.assertEqual(game.world.wave, 2)
        self.assertAlmostEqual(game.world.player.damage, 1.25)
        self.assertEqual(game.world.state, "playing")

    def test_full_navigation_saves_defeat_and_returns_to_menu(self):
        menu = self.show(MenuWindow(self.repo))
        QTest.mouseClick(menu.startButton, Qt.MouseButton.LeftButton)
        APP.processEvents()
        game = menu.game
        game.timer.stop()
        self.assertFalse(menu.isVisible())
        game.world.score = 123
        game.world.state = "game_over"

        def close_result():
            for widget in APP.topLevelWidgets():
                if isinstance(widget, ResultDialog):
                    QTest.mouseClick(widget.menuButton, Qt.MouseButton.LeftButton)

        QTimer.singleShot(30, close_result)
        game.finish_run(True)
        APP.processEvents()
        self.assertTrue(menu.isVisible())
        self.assertIsNone(menu.game)
        self.assertEqual(self.repo.runs()[0]["score"], 123)
        self.assertEqual(menu.profileStatsLabel.text(), "Рекорд: 123  /  Забегов: 1")

    def test_cancel_exit_resumes_play(self):
        game = self.game()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            game.request_menu()
        self.assertEqual(game.world.state, "playing")
        self.assertEqual(self.repo.runs(include_abandoned=True), [])

    def test_repeat_save_does_not_duplicate_result(self):
        game = self.game()
        game.world.score = 50
        self.assertTrue(game.save_result(True))
        self.assertTrue(game.save_result(True))
        self.assertEqual(len(self.repo.runs()), 1)

    def test_score_filter_and_export(self):
        menu = self.show(MenuWindow(self.repo))
        result = {
            "score": 400,
            "wave": 3,
            "kills": 12,
            "duration": 42,
            "difficulty": "Сложно",
            "completed": True,
            "upgrades": [],
        }
        self.repo.save_run("test", self.repo.players()[0]["id"], result)
        menu.refresh_scores()
        self.assertEqual(menu.scoresTable.rowCount(), 1)
        menu.scoreDifficultyCombo.setCurrentText("Легко")
        self.assertEqual(menu.scoresTable.rowCount(), 0)
        menu.scoreDifficultyCombo.setCurrentText("Сложно")
        target = Path(self.temp.name) / "scores.csv"
        with patch(
            "neonarena.windows.QFileDialog.getSaveFileName", return_value=(str(target), "")
        ):
            menu.export_scores()
        self.assertIn("400", target.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
