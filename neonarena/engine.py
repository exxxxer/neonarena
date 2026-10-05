"""Deterministic game simulation, independent of widgets and rendering."""

import math
import random
from dataclasses import dataclass, field

WIDTH = 1100
HEIGHT = 650
PLAYER_RADIUS = 14
OBSTACLES = ((245, 175, 65, 145), (790, 330, 65, 145), (510, 95, 80, 50), (510, 505, 80, 50))
DIFFICULTIES = {"Легко": 0.8, "Нормально": 1.0, "Сложно": 1.35}
UPGRADES = {
    "damage": ("Усилитель", "+25% к урону обоих видов оружия"),
    "rate": ("Разгон", "Интервал выстрелов на 15% меньше"),
    "speed": ("Ускоритель", "+12% к скорости движения"),
    "health": ("Броня", "+25 к максимуму здоровья и +25 HP"),
    "heal": ("Ремкомплект", "Восстановить 50 здоровья"),
    "dash": ("Импульс", "Перезарядка рывка на 20% быстрее"),
    "pierce": ("Пробой", "Пульсовый снаряд пробивает ещё одного врага"),
    "spread": ("Картечь", "Два дополнительных снаряда дробовика"),
}


def unit(x, y):
    length = math.hypot(x, y)
    return (x / length, y / length) if length > 0.00001 else (1.0, 0.0)


def segment_hit(ax, ay, bx, by, cx, cy, radius):
    """Swept collision prevents fast projectiles passing through targets."""
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = max(0, min(1, ((cx - ax) * dx + (cy - ay) * dy) / length)) if length else 0
    return (ax + t * dx - cx) ** 2 + (ay + t * dy - cy) ** 2 <= radius**2


def segment_rect(ax, ay, bx, by, rect):
    """Slab intersection against a wall's axis-aligned rectangle."""
    left, top, width, height = rect
    low, high = 0.0, 1.0
    for start, delta, lower, upper in (
        (ax, bx - ax, left, left + width),
        (ay, by - ay, top, top + height),
    ):
        if abs(delta) < 1e-9:
            if not lower <= start <= upper:
                return False
            continue
        a, b = (lower - start) / delta, (upper - start) / delta
        low, high = max(low, min(a, b)), min(high, max(a, b))
        if low > high:
            return False
    return True


def constrain(x, y, radius):
    x, y = max(radius, min(WIDTH - radius, x)), max(radius, min(HEIGHT - radius, y))
    for left, top, width, height in OBSTACLES:
        closest_x = max(left, min(left + width, x))
        closest_y = max(top, min(top + height, y))
        dx, dy = x - closest_x, y - closest_y
        distance = math.hypot(dx, dy)
        if 0 < distance < radius:
            x += dx / distance * (radius - distance)
            y += dy / distance * (radius - distance)
        elif distance == 0:
            exits = [
                (abs(x - left), left - radius, y),
                (abs(x - left - width), left + width + radius, y),
                (abs(y - top), x, top - radius),
                (abs(y - top - height), x, top + height + radius),
            ]
            _, x, y = min(exits)
    return x, y


@dataclass
class Player:
    x: float = WIDTH / 2
    y: float = HEIGHT / 2
    health: float = 100
    max_health: float = 100
    speed: float = 255
    damage: float = 1
    fire_interval: float = 1
    weapon: str = "pulse"
    fire_cooldown: float = 0
    dash_cooldown: float = 0
    dash_duration: float = 0
    dash_recharge: float = 2.4
    dash_x: float = 1
    dash_y: float = 0
    invulnerable: float = 0
    pierce: int = 0
    pellets: int = 5


@dataclass
class Enemy:
    id: int
    kind: str
    x: float
    y: float
    health: float
    radius: float
    speed: float
    timer: float = 1.6
    mode: str = "follow"
    direction_x: float = 0
    direction_y: float = 0
    flash: float = 0


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    friendly: bool = True
    life: float = 1.6
    pierce: int = 0
    hit_ids: set = field(default_factory=set)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: str
    life: float
    total: float


class World:
    def __init__(self, difficulty="Нормально", seed=None):
        if difficulty not in DIFFICULTIES:
            raise ValueError("Неизвестная сложность")
        self.difficulty = difficulty
        self.factor = DIFFICULTIES[difficulty]
        self.random = random.Random(seed)
        self.player = Player()
        self.enemies = []
        self.projectiles = []
        self.particles = []
        self.events = []
        self.state = "playing"
        self.wave = 0
        self.score = 0
        self.kills = 0
        self.elapsed = 0
        self.spawn_remaining = 0
        self.spawn_timer = 0
        self.wave_intro = 0
        self.upgrade_choices = []
        self.upgrades_taken = []
        self.enemy_counter = 0
        self.shots = 0
        self.hits = 0
        self.start_wave()

    def start_wave(self):
        self.wave += 1
        self.spawn_remaining = min(28, 5 + self.wave * 2)
        self.spawn_timer = 1.3
        self.wave_intro = 2.0
        self.state = "playing"
        self.projectiles.clear()
        self.events.append("wave")

    def spawn_enemy(self, kind=None, position=None):
        if kind is None:
            kinds = ["seeker"]
            if self.wave >= 2:
                kinds.append("shooter")
            if self.wave >= 3:
                kinds.append("charger")
            kind = self.random.choice(kinds)
        if kind not in ("seeker", "shooter", "charger"):
            raise ValueError("Неизвестный противник")
        if position is None:
            for _ in range(20):
                side = self.random.randrange(4)
                x = self.random.uniform(30, WIDTH - 30)
                y = self.random.uniform(30, HEIGHT - 30)
                x, y = [(25, y), (WIDTH - 25, y), (x, 25), (x, HEIGHT - 25)][side]
                if math.hypot(x - self.player.x, y - self.player.y) > 230:
                    break
        else:
            x, y = position
        health, radius, speed = {
            "seeker": (28, 14, 85),
            "shooter": (40, 17, 62),
            "charger": (65, 20, 73),
        }[kind]
        scale = 1 + (self.wave - 1) * 0.055
        self.enemy_counter += 1
        enemy = Enemy(
            self.enemy_counter,
            kind,
            x,
            y,
            health * scale * self.factor,
            radius,
            speed * min(1.7, scale) * self.factor,
        )
        self.enemies.append(enemy)
        return enemy

    def dash(self, move_x=0, move_y=0, aim_x=None, aim_y=None):
        player = self.player
        if self.state != "playing" or player.dash_cooldown > 0:
            return False
        if move_x == 0 and move_y == 0:
            move_x = (aim_x if aim_x is not None else player.x + 1) - player.x
            move_y = (aim_y if aim_y is not None else player.y) - player.y
        player.dash_x, player.dash_y = unit(move_x, move_y)
        player.dash_duration = 0.18
        player.dash_cooldown = player.dash_recharge
        player.invulnerable = max(player.invulnerable, 0.22)
        self.events.append("dash")
        return True

    def shoot(self, aim_x, aim_y):
        player = self.player
        if player.fire_cooldown > 0 or self.state != "playing":
            return
        angle = math.atan2(aim_y - player.y, aim_x - player.x)
        scatter = player.weapon == "scatter"
        angles = [angle]
        if scatter:
            angles = [angle + (i - (player.pellets - 1) / 2) * 0.11 for i in range(player.pellets)]
        for direction in angles:
            ux, uy = math.cos(direction), math.sin(direction)
            self.projectiles.append(
                Projectile(
                    player.x + ux * 19,
                    player.y + uy * 19,
                    ux * 710,
                    uy * 710,
                    (11 if scatter else 20) * player.damage,
                    pierce=0 if scatter else player.pierce,
                )
            )
            self.shots += 1
        player.fire_cooldown = (0.55 if scatter else 0.17) * player.fire_interval
        self.events.append("shot")

    def damage_player(self, amount):
        player = self.player
        if player.invulnerable > 0 or self.state != "playing":
            return
        player.health = max(0, player.health - amount * self.factor)
        player.invulnerable = 0.65
        self.burst(player.x, player.y, "#ff658f", 12)
        self.events.append("hurt")
        if player.health <= 0:
            self.state = "game_over"
            self.events.append("over")

    def burst(self, x, y, color, count=10):
        for _ in range(count):
            direction = self.random.uniform(0, math.tau)
            speed = self.random.uniform(45, 190)
            life = self.random.uniform(0.2, 0.55)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(direction) * speed,
                    math.sin(direction) * speed,
                    color,
                    life,
                    life,
                )
            )
        self.particles = self.particles[-400:]

    def update(self, dt, movement=(0, 0), aim=None, firing=False):
        if self.state != "playing":
            return
        dt = max(0, min(dt, 1 / 30))
        self.elapsed += dt
        self.wave_intro = max(0, self.wave_intro - dt)
        player = self.player
        for name in ("invulnerable", "fire_cooldown", "dash_cooldown"):
            setattr(player, name, max(0, getattr(player, name) - dt))
        mx, my = movement
        if player.dash_duration > 0:
            mx, my = player.dash_x, player.dash_y
            speed = 900
            player.dash_duration = max(0, player.dash_duration - dt)
            self.burst(player.x, player.y, "#57edff", 1)
        else:
            if mx or my:
                mx, my = unit(mx, my)
            speed = player.speed
        player.x, player.y = constrain(
            player.x + mx * speed * dt, player.y + my * speed * dt, PLAYER_RADIUS
        )
        if firing and aim:
            self.shoot(*aim)
        self.spawn_timer -= dt
        if self.spawn_remaining > 0 and self.spawn_timer <= 0:
            self.spawn_enemy()
            self.spawn_remaining -= 1
            self.spawn_timer = max(0.3, 0.9 - self.wave * 0.035)
        self.update_enemies(dt)
        self.update_projectiles(dt)
        self.update_particles(dt)
        if self.state == "playing" and self.spawn_remaining == 0 and not self.enemies:
            self.score += int(100 * self.wave * self.factor)
            self.upgrade_choices = self.random.sample(list(UPGRADES), 3)
            self.state = "upgrade"
            self.events.append("upgrade")

    def update_enemies(self, dt):
        player = self.player
        for enemy in self.enemies:
            enemy.flash = max(0, enemy.flash - dt)
            enemy.timer -= dt
            dx, dy = unit(player.x - enemy.x, player.y - enemy.y)
            distance = math.hypot(player.x - enemy.x, player.y - enemy.y)
            speed = enemy.speed
            if enemy.kind == "shooter":
                if distance < 185:
                    dx, dy = -dx, -dy
                elif distance < 300:
                    speed = 0
                if enemy.timer <= 0:
                    self.projectiles.append(
                        Projectile(enemy.x, enemy.y, dx * 230, dy * 230, 13, False, life=4)
                    )
                    shot = self.projectiles[-1]
                    shot.vx, shot.vy = unit(player.x - enemy.x, player.y - enemy.y)
                    shot.vx *= 230
                    shot.vy *= 230
                    enemy.timer = 1.7 / self.factor
            elif enemy.kind == "charger":
                if enemy.mode == "follow" and enemy.timer <= 0:
                    enemy.mode, enemy.timer = "windup", 0.65
                    enemy.direction_x, enemy.direction_y = dx, dy
                if enemy.mode == "windup":
                    speed = 0
                    if enemy.timer <= 0:
                        enemy.mode, enemy.timer = "charge", 0.6
                if enemy.mode == "charge":
                    dx, dy = enemy.direction_x, enemy.direction_y
                    speed = 385
                    if enemy.timer <= 0:
                        enemy.mode, enemy.timer = "follow", 2.0
            enemy.x, enemy.y = constrain(
                enemy.x + dx * speed * dt, enemy.y + dy * speed * dt, enemy.radius
            )
            if math.hypot(player.x - enemy.x, player.y - enemy.y) < PLAYER_RADIUS + enemy.radius:
                self.damage_player(16 if enemy.kind == "charger" else 11)

    def update_projectiles(self, dt):
        surviving = []
        for shot in self.projectiles:
            old_x, old_y = shot.x, shot.y
            shot.x += shot.vx * dt
            shot.y += shot.vy * dt
            shot.life -= dt
            if shot.life <= 0 or not 0 <= shot.x <= WIDTH or not 0 <= shot.y <= HEIGHT:
                continue
            if any(segment_rect(old_x, old_y, shot.x, shot.y, rect) for rect in OBSTACLES):
                self.burst(shot.x, shot.y, "#52677e", 3)
                continue
            consumed = False
            if shot.friendly:
                for enemy in self.enemies:
                    if enemy.health <= 0 or enemy.id in shot.hit_ids:
                        continue
                    if segment_hit(
                        old_x, old_y, shot.x, shot.y, enemy.x, enemy.y, enemy.radius + 3
                    ):
                        enemy.health -= shot.damage
                        enemy.flash = 0.1
                        self.hits += 1
                        shot.hit_ids.add(enemy.id)
                        self.burst(enemy.x, enemy.y, "#ff688e", 5)
                        if shot.pierce <= 0:
                            consumed = True
                            break
                        shot.pierce -= 1
            elif segment_hit(
                old_x, old_y, shot.x, shot.y, self.player.x, self.player.y, PLAYER_RADIUS + 4
            ):
                self.damage_player(shot.damage)
                consumed = True
            if not consumed:
                surviving.append(shot)
        self.projectiles = surviving[-500:]
        dead = [enemy for enemy in self.enemies if enemy.health <= 0]
        for enemy in dead:
            self.kills += 1
            self.score += int(
                {"seeker": 20, "shooter": 35, "charger": 50}[enemy.kind] * self.factor
            )
            self.burst(enemy.x, enemy.y, "#ff688e", 18)
            self.events.append("kill")
        self.enemies = [enemy for enemy in self.enemies if enemy.health > 0]

    def update_particles(self, dt):
        for particle in self.particles:
            particle.life -= dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
        self.particles = [particle for particle in self.particles if particle.life > 0]

    def choose_upgrade(self, key):
        if self.state != "upgrade" or key not in self.upgrade_choices:
            raise ValueError("Это улучшение сейчас недоступно")
        player = self.player
        if key == "damage":
            player.damage *= 1.25
        elif key == "rate":
            player.fire_interval = max(0.32, player.fire_interval * 0.85)
        elif key == "speed":
            player.speed = min(430, player.speed * 1.12)
        elif key == "health":
            player.max_health += 25
            player.health += 25
        elif key == "heal":
            player.health = min(player.max_health, player.health + 50)
        elif key == "dash":
            player.dash_recharge = max(0.65, player.dash_recharge * 0.8)
        elif key == "pierce":
            player.pierce = min(6, player.pierce + 1)
        elif key == "spread":
            player.pellets = min(13, player.pellets + 2)
        self.upgrades_taken.append(key)
        self.upgrade_choices = []
        self.start_wave()

    def pause(self):
        if self.state == "playing":
            self.state = "paused"

    def resume(self):
        if self.state == "paused":
            self.state = "playing"

    def result(self, completed=True):
        return {
            "score": self.score,
            "wave": self.wave,
            "kills": self.kills,
            "duration": round(self.elapsed, 2),
            "difficulty": self.difficulty,
            "completed": completed,
            "upgrades": list(self.upgrades_taken),
        }
