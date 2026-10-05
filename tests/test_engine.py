"""Pure simulation tests for combat, movement and wave progression."""

import math
import unittest

from neonarena.engine import (
    HEIGHT,
    OBSTACLES,
    UPGRADES,
    WIDTH,
    Projectile,
    World,
    constrain,
    segment_hit,
    segment_rect,
)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.world = World(seed=123)
        self.world.spawn_remaining = 1
        self.world.spawn_timer = 1000

    def step(self, duration, **kwargs):
        for _ in range(round(duration * 120)):
            self.world.update(1 / 120, **kwargs)

    def test_diagonal_movement_is_normalized(self):
        start = (self.world.player.x, self.world.player.y)
        self.step(0.1, movement=(1, 1))
        distance = math.hypot(self.world.player.x - start[0], self.world.player.y - start[1])
        self.assertAlmostEqual(distance, self.world.player.speed * 0.1)

    def test_arena_boundaries_and_obstacles(self):
        self.assertEqual(constrain(-100, 900, 14), (14, HEIGHT - 14))
        x, y = constrain(260, 220, 14)
        left, top, width, height = OBSTACLES[0]
        self.assertFalse(left <= x <= left + width and top <= y <= top + height)

    def test_pause_freezes_everything(self):
        self.world.pause()
        self.step(1, movement=(1, 0), aim=(800, 300), firing=True)
        self.assertEqual(self.world.elapsed, 0)
        self.assertEqual(len(self.world.projectiles), 0)
        self.world.resume()
        self.step(0.1)
        self.assertGreater(self.world.elapsed, 0)

    def test_dash_recharge_and_invulnerability(self):
        self.assertTrue(self.world.dash(1, 0))
        self.assertFalse(self.world.dash(1, 0))
        self.world.damage_player(50)
        self.assertEqual(self.world.player.health, 100)
        self.step(2.5)
        self.assertTrue(self.world.dash(0, 1))

    def test_shot_cooldown_and_weapon_spread(self):
        self.world.shoot(900, 325)
        self.world.shoot(900, 325)
        self.assertEqual(len(self.world.projectiles), 1)
        self.world.player.fire_cooldown = 0
        self.world.player.weapon = "scatter"
        self.world.shoot(900, 325)
        self.assertEqual(len(self.world.projectiles), 6)

    def test_projectile_kill_scores_once(self):
        enemy = self.world.spawn_enemy("seeker", (650, 325))
        enemy.health = 15
        self.step(0.3, aim=(800, 325), firing=True)
        self.assertEqual(self.world.kills, 1)
        self.assertEqual(self.world.score, 20)
        self.assertEqual(len(self.world.enemies), 0)

    def test_fast_projectile_swept_collision(self):
        self.assertTrue(segment_hit(0, 100, 200, 100, 110, 100, 10))
        self.assertFalse(segment_hit(0, 100, 200, 100, 110, 130, 10))

    def test_wall_stops_projectile(self):
        self.assertTrue(segment_rect(200, 220, 330, 220, OBSTACLES[0]))
        self.world.projectiles.append(Projectile(238, 220, 710, 0, 20))
        self.world.update_projectiles(1 / 60)
        self.assertEqual(self.world.projectiles, [])

    def test_piercing_hits_each_enemy_once(self):
        first = self.world.spawn_enemy("seeker", (625, 325))
        second = self.world.spawn_enemy("seeker", (655, 325))
        first.speed = second.speed = 0
        self.world.player.pierce = 1
        self.world.shoot(900, 325)
        self.step(0.2)
        self.assertEqual(self.world.hits, 2)
        self.assertEqual(first.health, 8)
        self.assertEqual(second.health, 8)

    def test_damage_cooldown_and_game_over(self):
        self.world.damage_player(25)
        self.world.damage_player(25)
        self.assertEqual(self.world.player.health, 75)
        self.world.player.invulnerable = 0
        self.world.damage_player(200)
        self.assertEqual(self.world.state, "game_over")
        self.assertEqual(self.world.player.health, 0)
        elapsed = self.world.elapsed
        self.step(1)
        self.assertEqual(self.world.elapsed, elapsed)

    def test_wave_clear_requires_all_spawns_and_enemies(self):
        self.step(0.02)
        self.assertEqual(self.world.state, "playing")
        self.world.spawn_remaining = 0
        enemy = self.world.spawn_enemy("seeker", (900, 325))
        self.step(0.02)
        self.assertEqual(self.world.state, "playing")
        enemy.health = 0
        self.step(0.02)
        self.assertEqual(self.world.state, "upgrade")
        self.assertEqual(len(set(self.world.upgrade_choices)), 3)
        old_wave = self.world.wave
        key = self.world.upgrade_choices[0]
        self.world.choose_upgrade(key)
        self.assertEqual(self.world.wave, old_wave + 1)
        self.assertEqual(self.world.state, "playing")
        self.assertIn(key, self.world.upgrades_taken)

    def test_upgrade_validation_and_health_limit(self):
        with self.assertRaises(ValueError):
            self.world.choose_upgrade("heal")
        self.world.state = "upgrade"
        self.world.upgrade_choices = ["heal"]
        self.world.choose_upgrade("heal")
        self.assertEqual(self.world.player.health, self.world.player.max_health)

    def test_all_upgrades_change_expected_stat(self):
        attributes = {
            "damage": "damage",
            "rate": "fire_interval",
            "speed": "speed",
            "health": "max_health",
            "heal": "health",
            "dash": "dash_recharge",
            "pierce": "pierce",
            "spread": "pellets",
        }
        for key in UPGRADES:
            world = World(seed=1)
            world.player.health = 30
            before = getattr(world.player, attributes[key])
            world.state = "upgrade"
            world.upgrade_choices = [key]
            world.choose_upgrade(key)
            self.assertNotEqual(getattr(world.player, attributes[key]), before)

    def test_shooter_aims_toward_player_when_retreating(self):
        enemy = self.world.spawn_enemy("shooter", (self.world.player.x + 100, 325))
        enemy.timer = 0
        self.world.update_enemies(1 / 120)
        shot = self.world.projectiles[0]
        self.assertFalse(shot.friendly)
        self.assertLess(shot.vx, 0)

    def test_charger_telegraphs_then_charges(self):
        enemy = self.world.spawn_enemy("charger", (900, 325))
        enemy.timer = 0
        self.world.update_enemies(1 / 120)
        self.assertEqual(enemy.mode, "windup")
        x = enemy.x
        self.world.update_enemies(0.2)
        self.assertEqual(enemy.x, x)
        enemy.timer = 0
        self.world.update_enemies(1 / 120)
        self.assertEqual(enemy.mode, "charge")
        self.assertLess(enemy.x, x)

    def test_enemy_projectile_damage_and_bounds(self):
        player = self.world.player
        self.world.projectiles.append(Projectile(player.x - 10, player.y, 230, 0, 13, False))
        self.world.update_projectiles(0.02)
        self.assertEqual(player.health, 87)
        self.world.projectiles.append(Projectile(WIDTH - 2, 325, 710, 0, 20))
        self.world.update_projectiles(0.02)
        self.assertEqual(self.world.projectiles, [])

    def test_deterministic_spawns(self):
        other = World(seed=123)
        for _ in range(5):
            a = self.world.spawn_enemy()
            b = other.spawn_enemy()
            self.assertEqual((a.kind, a.x, a.y), (b.kind, b.x, b.y))

    def test_spawn_schedule_has_seven_enemies_on_first_wave(self):
        world = World(seed=1)
        world.player.invulnerable = 100
        for _ in range(120 * 9):
            world.update(1 / 120)
        self.assertEqual(world.spawn_remaining, 0)
        self.assertEqual(len(world.enemies), 7)


if __name__ == "__main__":
    unittest.main()
