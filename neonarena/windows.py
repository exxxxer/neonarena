"""Designer form controllers, fixed-step game loop and desktop navigation."""

import csv
import sqlite3
import uuid
from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import QElapsedTimer, QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
)

from .audio import Audio
from .canvas import ArenaCanvas
from .engine import UPGRADES, World
from .storage import resource

HELP = (
    "WASD или стрелки — движение.\nЛКМ удерживать — стрельба.\n"
    "1 — пульсовый бластер; 2 — дробовик; Q или ПКМ — смена оружия.\n"
    "Space — рывок в сторону движения, без движения — к прицелу.\n"
    "Esc / P — пауза; F11 — полный экран; F12 — сохранить снимок.\n\n"
    "Розовые треугольники преследуют игрока. Фиолетовые ромбы стреляют.\n"
    "Жёлтые шестиугольники готовят рывок: избегайте линии атаки.\n"
    "Препятствия останавливают движение и снаряды. Рывок даёт краткую защиту.\n\n"
    "После каждой волны выберите усиление. Волны бесконечны.\n"
    "Рекорды учитывают забеги, завершившиеся поражением; прерванные хранятся отдельно."
)


class SettingsDialog(QDialog):
    def __init__(self, repository, parent=None):
        super().__init__(parent)
        uic.loadUi(resource("ui/settings.ui"), self)
        self.repository = repository
        self.volumeSlider.setValue(repository.setting("volume", 55))
        self.muteCheck.setChecked(repository.setting("muted", False))
        self.fullscreenCheck.setChecked(repository.setting("fullscreen", False))
        self.particlesCheck.setChecked(repository.setting("particles", True))
        self.volumeSlider.valueChanged.connect(
            lambda value: self.volumeLabel.setText(f"Громкость: {value}%")
        )
        self.volumeLabel.setText(f"Громкость: {self.volumeSlider.value()}%")
        self.saveButton.clicked.connect(self.save)
        self.cancelButton.clicked.connect(self.reject)

    def save(self):
        self.repository.save_settings(
            {
                "volume": self.volumeSlider.value(),
                "muted": self.muteCheck.isChecked(),
                "fullscreen": self.fullscreenCheck.isChecked(),
                "particles": self.particlesCheck.isChecked(),
            }
        )
        self.accept()


class UpgradeDialog(QDialog):
    def __init__(self, world, parent=None):
        super().__init__(parent)
        uic.loadUi(resource("ui/upgrade.ui"), self)
        self.selected = None
        self.titleLabel.setText(f"ВОЛНА {world.wave:02d} ЗАЧИЩЕНА")
        self.shortcuts = []
        for index, key in enumerate(world.upgrade_choices):
            title, description = UPGRADES[key]
            button = getattr(self, f"upgradeButton{index}")
            button.setText(f"{index + 1}  /  {title}\n{description}")
            button.clicked.connect(lambda _checked=False, choice=key: self.choose(choice))
            binding = QShortcut(QKeySequence(str(index + 1)), self)
            binding.activated.connect(lambda choice=key: self.choose(choice))
            self.shortcuts.append(binding)
        self.quitButton.clicked.connect(self.accept)

    def choose(self, key):
        self.selected = key
        self.accept()

    def reject(self):
        # Leaving an unanswered upgrade cannot start a new wave.
        return


class ResultDialog(QDialog):
    def __init__(self, world, name, saved, best, completed, parent=None):
        super().__init__(parent)
        uic.loadUi(resource("ui/result.ui"), self)
        self.again = False
        self.titleLabel.setText("ЗАБЕГ ЗАВЕРШЁН" if completed else "ЗАБЕГ ПРЕРВАН")
        self.subtitleLabel.setText(f"{name}  /  {world.difficulty}")
        self.scoreLabel.setText(f"{world.score:,} ОЧКОВ".replace(",", " "))
        self.scoreLabel.setStyleSheet("font-size: 48px; color: #57edff; font-weight: 800")
        self.detailsLabel.setText(
            f"Волна: {world.wave}    •    Убийств: {world.kills}\n"
            f"Время в бою: {int(world.elapsed // 60):02d}:{int(world.elapsed % 60):02d}\n"
            f"Личный рекорд: {best}"
        )
        names = [UPGRADES[key][0] for key in world.upgrades_taken]
        self.upgradesLabel.setText("Усиления: " + (", ".join(names) if names else "нет"))
        self.saveStatusLabel.setText(
            "Результат сохранён" if saved else "Ошибка сохранения результата"
        )
        self.againButton.clicked.connect(self.restart)
        self.menuButton.clicked.connect(self.accept)

    def restart(self):
        self.again = True
        self.accept()


class MenuWindow(QMainWindow):
    def __init__(self, repository):
        super().__init__()
        uic.loadUi(resource("ui/menu.ui"), self)
        self.repository = repository
        self.game = None
        self.homeLayout.setStretch(0, 4)
        self.homeLayout.setStretch(1, 5)
        self.previewLabel.setPixmap(
            QPixmap(str(resource("assets/banner.svg"))).scaled(
                560,
                260,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.guideBrowser.setHtml(
            '<h2 style="color:#b38aff">Три угрозы. Два оружия.</h2>'
            '<p><b style="color:#ff658f">ПРЕСЛЕДОВАТЕЛЬ</b><br>'
            "Идёт прямо на тебя. Держи дистанцию.</p>"
            '<p><b style="color:#b38aff">СТРЕЛОК</b><br>'
            "Появляется со второй волны. Укрывайся за блоками.</p>"
            '<p><b style="color:#ffbe68">ТАРАН</b><br>'
            "Появляется с третьей волны. Линия показывает направление атаки.</p>"
            '<p><b style="color:#57edff">ТВОЙ ВЫБОР</b><br>'
            "Пульс точен на дистанции. Дробовик эффективен вблизи. "
            "Рывок позволяет пройти через опасный момент.</p>"
        )
        self.difficultyCombo.setCurrentText(repository.setting("difficulty", "Нормально"))
        self.scoresTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.scoresTable.verticalHeader().hide()
        self.playerCombo.currentIndexChanged.connect(self.profile_changed)
        self.startButton.clicked.connect(self.start_game)
        self.addPlayerButton.clicked.connect(self.add_player)
        self.renamePlayerButton.clicked.connect(self.rename_player)
        self.deletePlayerButton.clicked.connect(self.delete_player)
        self.settingsButton.clicked.connect(lambda: SettingsDialog(repository, self).exec())
        self.helpButton.clicked.connect(lambda: QMessageBox.information(self, "Как играть", HELP))
        self.quitButton.clicked.connect(self.close)
        self.exportButton.clicked.connect(self.export_scores)
        self.scoreDifficultyCombo.currentTextChanged.connect(self.refresh_scores)
        self.mineCheck.toggled.connect(self.refresh_scores)
        self.abandonedCheck.toggled.connect(self.refresh_scores)
        self.refresh_profiles(repository.setting("player_id"))
        self.statusbar.showMessage("Локальные профили и рекорды  •  Игра работает без интернета")

    def refresh_profiles(self, selected_id=None):
        previous = selected_id if selected_id is not None else self.playerCombo.currentData()
        self.playerCombo.blockSignals(True)
        self.playerCombo.clear()
        for player in self.repository.players():
            self.playerCombo.addItem(player["name"], player["id"])
        index = self.playerCombo.findData(previous)
        self.playerCombo.setCurrentIndex(max(0, index) if self.playerCombo.count() else -1)
        self.playerCombo.blockSignals(False)
        self.profile_changed()

    def profile_changed(self, *_args):
        player = self.repository.player(self.playerCombo.currentData())
        for button in (self.startButton, self.renamePlayerButton, self.deletePlayerButton):
            button.setEnabled(player is not None)
        self.profileStatsLabel.setText(
            f"Рекорд: {player['best_score']}  /  Забегов: {player['games']}"
            if player
            else "Создай профиль, чтобы начать"
        )
        if player:
            self.repository.save_settings({"player_id": player["id"]})
        self.refresh_scores()

    def add_player(self):
        name, accepted = QInputDialog.getText(self, "Новый профиль", "Имя игрока:")
        if accepted:
            try:
                player_id = self.repository.save_player(name)
            except ValueError as error:
                QMessageBox.warning(self, "Проверь имя", str(error))
                return
            self.refresh_profiles(player_id)

    def rename_player(self):
        player = self.repository.player(self.playerCombo.currentData())
        if not player:
            return
        name, accepted = QInputDialog.getText(
            self, "Имя профиля", "Новое имя:", text=player["name"]
        )
        if accepted:
            try:
                self.repository.save_player(name, player["id"])
            except ValueError as error:
                QMessageBox.warning(self, "Проверь имя", str(error))
                return
            self.refresh_profiles(player["id"])

    def delete_player(self):
        player_id = self.playerCombo.currentData()
        if player_id is None:
            return
        response = QMessageBox.question(
            self,
            "Удалить профиль",
            "Удалить профиль и все его забеги?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self.repository.delete_player(player_id)
            self.refresh_profiles()

    def score_rows(self):
        selected = self.playerCombo.currentData() if self.mineCheck.isChecked() else None
        if self.mineCheck.isChecked() and selected is None:
            return []
        return self.repository.runs(
            self.scoreDifficultyCombo.currentText(), selected, self.abandonedCheck.isChecked()
        )

    def refresh_scores(self, *_args):
        rows = self.score_rows()
        self.scoresTable.setRowCount(len(rows))
        for index, run in enumerate(rows):
            duration = f"{int(run['duration'] // 60):02d}:{int(run['duration'] % 60):02d}"
            values = [
                run["name"],
                run["score"],
                run["wave"],
                run["kills"],
                duration,
                run["difficulty"],
                "Поражение" if run["completed"] else "Прерван",
            ]
            for column, value in enumerate(values):
                self.scoresTable.setItem(index, column, QTableWidgetItem(str(value)))

    def export_scores(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт рекордов", "neon-arena.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(
                    [
                        "Игрок",
                        "Очки",
                        "Волна",
                        "Убийства",
                        "Секунды",
                        "Сложность",
                        "Завершён",
                        "Дата",
                    ]
                )
                for run in self.score_rows():
                    # Spreadsheet applications must treat user names as text.
                    name = run["name"]
                    if name.startswith(("=", "+", "-", "@")):
                        name = "'" + name
                    writer.writerow(
                        [
                            name,
                            run["score"],
                            run["wave"],
                            run["kills"],
                            run["duration"],
                            run["difficulty"],
                            run["completed"],
                            run["played_at"],
                        ]
                    )
        except OSError as error:
            QMessageBox.warning(self, "Ошибка экспорта", str(error))

    def start_game(self):
        player_id = self.playerCombo.currentData()
        if player_id is None or self.game is not None:
            return
        difficulty = self.difficultyCombo.currentText()
        self.repository.save_settings({"difficulty": difficulty})
        self.game = GameWindow(self.repository, player_id, difficulty)
        self.game.exit_requested.connect(self.game_finished)
        self.game.show()
        if self.repository.setting("fullscreen", False):
            self.game.showFullScreen()
        self.hide()

    def game_finished(self, again):
        self.game = None
        self.refresh_profiles()
        self.show()
        if again:
            QTimer.singleShot(0, self.start_game)


class GameWindow(QMainWindow):
    exit_requested = pyqtSignal(bool)

    def __init__(self, repository, player_id, difficulty):
        super().__init__()
        uic.loadUi(resource("ui/game.ui"), self)
        self.repository, self.player_id = repository, player_id
        self.world = World(difficulty)
        self.run_key = str(uuid.uuid4())
        self.recorded = False
        self.finished = False
        self.modal = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.canvas = ArenaCanvas(self.world, self)
        self.arenaLayout.addWidget(self.canvas)
        self.arenaLayout.setContentsMargins(0, 0, 0, 0)
        self.rootLayout.setStretch(2, 1)
        self.audio = Audio(
            repository.setting("volume", 55), repository.setting("muted", False), self
        )
        self.particles_enabled = repository.setting("particles", True)
        self.canvas.pause_requested.connect(self.toggle_pause)
        self.pauseButton.clicked.connect(self.toggle_pause)
        self.menuButton.clicked.connect(self.request_menu)
        self.bindings = []
        for sequence, callback in (("F11", self.toggle_fullscreen), ("F12", self.screenshot)):
            binding = QShortcut(QKeySequence(sequence), self)
            binding.activated.connect(callback)
            self.bindings.append(binding)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.accumulator = 0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.update_hud()
        QTimer.singleShot(0, self.canvas.setFocus)

    def tick(self):
        elapsed = min(0.1, self.clock.restart() / 1000)
        if self.world.state == "playing":
            self.accumulator += elapsed
            while self.accumulator >= 1 / 120:
                self.world.update(
                    1 / 120, self.canvas.movement(), self.canvas.aim, self.canvas.firing
                )
                self.accumulator -= 1 / 120
                if self.world.state != "playing":
                    self.accumulator = 0
                    break
        else:
            self.accumulator = 0
        if not self.particles_enabled:
            self.world.particles.clear()
        for event in set(self.world.events):
            self.audio.play(event)
        self.world.events.clear()
        self.update_hud()
        self.canvas.update()
        if self.world.state == "upgrade" and not self.modal:
            self.select_upgrade()
        elif self.world.state == "game_over" and not self.modal:
            self.finish_run(True)

    def update_hud(self):
        world, player = self.world, self.world.player
        self.waveLabel.setText(f"ВОЛНА {world.wave:02d}")
        self.scoreLabel.setText(f"ОЧКИ {world.score}")
        self.killsLabel.setText(f"УБИЙСТВА {world.kills}")
        self.healthLabel.setText(f"{int(player.health)} / {int(player.max_health)} HP")
        self.healthBar.setMaximum(int(player.max_health))
        self.healthBar.setValue(int(player.health))
        self.healthBar.setTextVisible(False)
        self.weaponLabel.setText("[1] ПУЛЬС" if player.weapon == "pulse" else "[2] ДРОБОВИК")
        self.dashLabel.setText(
            "Рывок готов" if player.dash_cooldown <= 0 else f"Рывок: {player.dash_cooldown:.1f}с"
        )
        self.pauseButton.setText("Продолжить" if world.state == "paused" else "Пауза")

    def toggle_pause(self):
        if self.modal:
            return
        if self.world.state == "playing":
            self.world.pause()
        elif self.world.state == "paused":
            self.world.resume()
        self.canvas.clear_input()
        self.clock.restart()
        self.accumulator = 0
        self.canvas.setFocus()
        self.update_hud()
        self.canvas.update()

    def select_upgrade(self):
        self.modal = True
        self.timer.stop()
        self.canvas.clear_input()
        dialog = UpgradeDialog(self.world, self)
        dialog.exec()
        if dialog.selected is None:
            self.modal = False
            self.finish_run(False)
            return
        self.world.choose_upgrade(dialog.selected)
        self.modal = False
        self.clock.restart()
        self.timer.start()
        self.canvas.setFocus()

    def save_result(self, completed):
        if self.recorded:
            return True
        try:
            self.repository.save_run(self.run_key, self.player_id, self.world.result(completed))
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.warning(self, "Результат не сохранён", str(error))
            return False
        self.recorded = True
        return True

    def finish_run(self, completed):
        self.timer.stop()
        self.canvas.clear_input()
        self.modal = True
        saved = self.save_result(completed)
        player = self.repository.player(self.player_id)
        dialog = ResultDialog(
            self.world, player["name"], saved, player["best_score"], completed, self
        )
        dialog.exec()
        self.finished = True
        self.exit_requested.emit(dialog.again)
        self.close()

    def request_menu(self):
        if self.modal:
            return
        was_playing = self.world.state == "playing"
        self.world.pause()
        self.canvas.clear_input()
        answer = QMessageBox.question(
            self,
            "Завершить забег",
            "Вернуться в меню? Забег сохранится как прерванный.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.finish_run(False)
        elif was_playing:
            self.world.resume()
            self.canvas.setFocus()
        self.clock.restart()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
        self.canvas.setFocus()

    def screenshot(self):
        if self.modal:
            return
        image = self.grab()
        was_playing = self.world.state == "playing"
        self.world.pause()
        self.canvas.clear_input()
        path, _ = QFileDialog.getSaveFileName(self, "Снимок арены", "NeonArena.png", "PNG (*.png)")
        if path and not image.save(path):
            QMessageBox.warning(self, "Ошибка снимка", "Не удалось записать изображение.")
        if was_playing:
            self.world.resume()
        self.clock.restart()
        self.canvas.setFocus()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and hasattr(self, "world"):
            if not self.isActiveWindow() and not self.modal:
                self.world.pause()
                self.canvas.clear_input()
        super().changeEvent(event)

    def closeEvent(self, event):
        if self.finished:
            event.accept()
            return
        event.ignore()
        self.request_menu()
