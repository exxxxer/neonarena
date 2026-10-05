"""Qt arena drawing, coordinate transforms and physical input events."""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from .engine import HEIGHT, OBSTACLES, WIDTH


class ArenaCanvas(QWidget):
    pause_requested = pyqtSignal()
    weapon_changed = pyqtSignal()

    def __init__(self, world, parent=None):
        super().__init__(parent)
        self.world = world
        self.keys = set()
        self.firing = False
        self.aim = (WIDTH / 2 + 100, HEIGHT / 2)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(700, 410)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def transform(self):
        scale = min(self.width() / WIDTH, self.height() / HEIGHT)
        return scale, (self.width() - WIDTH * scale) / 2, (self.height() - HEIGHT * scale) / 2

    def world_position(self, point):
        scale, ox, oy = self.transform()
        return (point.x() - ox) / scale, (point.y() - oy) / scale

    def movement(self):
        return (
            int(Qt.Key.Key_D in self.keys or Qt.Key.Key_Right in self.keys)
            - int(Qt.Key.Key_A in self.keys or Qt.Key.Key_Left in self.keys),
            int(Qt.Key.Key_S in self.keys or Qt.Key.Key_Down in self.keys)
            - int(Qt.Key.Key_W in self.keys or Qt.Key.Key_Up in self.keys),
        )

    def clear_input(self):
        self.keys.clear()
        self.firing = False

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_P) and not event.isAutoRepeat():
            self.clear_input()
            self.pause_requested.emit()
        elif key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.world.dash(*self.movement(), *self.aim)
        elif key in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_Q) and not event.isAutoRepeat():
            if self.world.state == "playing":
                self.world.player.weapon = (
                    "pulse"
                    if key == Qt.Key.Key_1
                    else "scatter"
                    if key == Qt.Key.Key_2
                    else "scatter"
                    if self.world.player.weapon == "pulse"
                    else "pulse"
                )
                self.weapon_changed.emit()
        else:
            self.keys.add(key)
        event.accept()

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self.keys.discard(event.key())
        event.accept()

    def mouseMoveEvent(self, event):
        self.aim = self.world_position(event.position())

    def mousePressEvent(self, event):
        self.setFocus()
        self.aim = self.world_position(event.position())
        if event.button() == Qt.MouseButton.LeftButton:
            self.firing = True
        elif event.button() == Qt.MouseButton.RightButton and self.world.state == "playing":
            self.world.player.weapon = (
                "scatter" if self.world.player.weapon == "pulse" else "pulse"
            )
            self.weapon_changed.emit()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.firing = False

    def focusOutEvent(self, event):
        self.clear_input()
        super().focusOutEvent(event)

    @staticmethod
    def glow(painter, x, y, radius, color):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for extra, alpha in ((9, 14), (5, 30), (1, 100)):
            ink = QColor(color)
            ink.setAlpha(alpha)
            painter.setPen(QPen(ink, 3))
            painter.drawEllipse(QPointF(x, y), radius + extra, radius + extra)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#070b17"))
        scale, ox, oy = self.transform()
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        painter.setClipRect(QRectF(0, 0, WIDTH, HEIGHT))
        painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), QColor("#0b1123"))
        painter.setPen(QPen(QColor("#17233c"), 1))
        for x in range(0, WIDTH, 40):
            painter.drawLine(QPointF(x, 0), QPointF(x, HEIGHT))
        for y in range(0, HEIGHT, 40):
            painter.drawLine(QPointF(0, y), QPointF(WIDTH, y))
        painter.setPen(QPen(QColor("#304c68"), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(4, 4, WIDTH - 8, HEIGHT - 8), 10, 10)
        for index, (x, y, width, height) in enumerate(OBSTACLES):
            painter.setBrush(QColor("#151f34"))
            painter.setPen(QPen(QColor("#48627c"), 2))
            painter.drawRoundedRect(QRectF(x, y, width, height), 5, 5)
            painter.setFont(QFont("DejaVu Sans", 9))
            painter.setPen(QColor("#50657f"))
            painter.drawText(
                QRectF(x, y, width, height), Qt.AlignmentFlag.AlignCenter, f"0{index + 1}"
            )
        for particle in self.world.particles:
            color = QColor(particle.color)
            color.setAlpha(int(255 * particle.life / particle.total))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(particle.x, particle.y), 2.5, 2.5)
        for shot in self.world.projectiles:
            color = "#57edff" if shot.friendly else "#ffbe68"
            painter.setPen(QPen(QColor(color), 3 if shot.friendly else 5))
            ux, uy = shot.vx / 710, shot.vy / 710
            painter.drawLine(QPointF(shot.x - ux * 12, shot.y - uy * 12), QPointF(shot.x, shot.y))
        for enemy in self.world.enemies:
            self.draw_enemy(painter, enemy)
        player = self.world.player
        self.glow(painter, player.x, player.y, 17, "#57edff")
        if player.invulnerable > 0:
            painter.setPen(QPen(QColor("#dbfcff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(player.x, player.y), 25, 25)
        painter.save()
        painter.translate(player.x, player.y)
        angle = math.degrees(math.atan2(self.aim[1] - player.y, self.aim[0] - player.x))
        painter.rotate(angle)
        path = QPainterPath()
        path.moveTo(21, 0)
        path.lineTo(-12, -13)
        path.lineTo(-6, 0)
        path.lineTo(-12, 13)
        path.closeSubpath()
        painter.setPen(QPen(QColor("#c8faff"), 2))
        painter.setBrush(QColor("#35bdd6"))
        painter.drawPath(path)
        painter.restore()
        ax, ay = self.aim
        painter.setPen(QPen(QColor("#6794ac"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(ax, ay), 9, 9)
        for dx, dy in ((14, 0), (-14, 0), (0, 14), (0, -14)):
            painter.drawLine(QPointF(ax + dx * 0.7, ay + dy * 0.7), QPointF(ax + dx, ay + dy))
        if self.world.wave_intro > 0 and self.world.state == "playing":
            painter.setFont(QFont("DejaVu Sans", 26, QFont.Weight.Bold))
            painter.setPen(QColor("#d9edff"))
            painter.drawText(
                QRectF(0, 230, WIDTH, 60),
                Qt.AlignmentFlag.AlignCenter,
                f"ВОЛНА {self.world.wave:02d}",
            )
        if self.world.state in ("paused", "game_over", "upgrade"):
            painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), QColor(5, 9, 20, 185))
            title = {
                "paused": "ПАУЗА",
                "game_over": "ЗАБЕГ ЗАВЕРШЁН",
                "upgrade": "ВОЛНА ЗАЧИЩЕНА",
            }[self.world.state]
            painter.setFont(QFont("DejaVu Sans", 30, QFont.Weight.Bold))
            painter.setPen(QColor("#57edff"))
            painter.drawText(QRectF(0, 245, WIDTH, 70), Qt.AlignmentFlag.AlignCenter, title)
            if self.world.state == "paused":
                painter.setFont(QFont("DejaVu Sans", 12))
                painter.setPen(QColor("#b0bfd5"))
                painter.drawText(
                    QRectF(0, 325, WIDTH, 40),
                    Qt.AlignmentFlag.AlignCenter,
                    "Esc / P — продолжить   •   кнопка Меню — завершить забег",
                )

    def draw_enemy(self, painter, enemy):
        color = {"seeker": "#ff658f", "shooter": "#b38aff", "charger": "#ffbe68"}[enemy.kind]
        self.glow(painter, enemy.x, enemy.y, enemy.radius, color)
        painter.setPen(QPen(QColor("#ffffff" if enemy.flash > 0 else color), 2))
        painter.setBrush(QColor("#4c253f" if enemy.kind == "seeker" else "#322844"))
        points = 3 if enemy.kind == "seeker" else 4 if enemy.kind == "shooter" else 6
        angle = math.atan2(self.world.player.y - enemy.y, self.world.player.x - enemy.x)
        path = QPainterPath()
        for index in range(points):
            direction = angle + index * math.tau / points
            point = QPointF(
                enemy.x + math.cos(direction) * enemy.radius,
                enemy.y + math.sin(direction) * enemy.radius,
            )
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        painter.drawPath(path)
        if enemy.mode == "windup":
            painter.setPen(QPen(QColor("#ffbe68"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(
                QPointF(enemy.x, enemy.y),
                QPointF(enemy.x + enemy.direction_x * 240, enemy.y + enemy.direction_y * 240),
            )
