"""Persistence, profile CRUD, atomic scoring and duplicate-run protection."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from neonarena.storage import Repository


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.repo = Repository(self.path)
        self.player_id = self.repo.players()[0]["id"]
        self.result = {
            "score": 250,
            "wave": 2,
            "kills": 8,
            "duration": 32.5,
            "difficulty": "Нормально",
            "completed": True,
            "upgrades": ["damage"],
        }

    def tearDown(self):
        self.repo.close()
        self.temp.cleanup()

    def test_profile_create_rename_and_unicode_unique(self):
        player_id = self.repo.save_player("Андрей")
        with self.assertRaises(ValueError):
            self.repo.save_player("АНДРЕЙ")
        self.repo.save_player("Новое имя", player_id)
        self.assertEqual(self.repo.player(player_id)["name"], "Новое имя")
        with self.assertRaises(ValueError):
            self.repo.save_player(" " * 3)

    def test_run_updates_stats_atomically_and_once(self):
        self.assertTrue(self.repo.save_run("a", self.player_id, self.result))
        self.assertFalse(self.repo.save_run("a", self.player_id, self.result))
        player = self.repo.player(self.player_id)
        self.assertEqual(
            (player["best_score"], player["games"], player["total_kills"]), (250, 1, 8)
        )

    def test_abandoned_does_not_change_best(self):
        self.result["completed"] = False
        self.repo.save_run("a", self.player_id, self.result)
        self.assertEqual(self.repo.player(self.player_id)["best_score"], 0)
        self.assertEqual(self.repo.runs(), [])
        self.assertEqual(len(self.repo.runs(include_abandoned=True)), 1)

    def test_personal_and_difficulty_filters(self):
        self.repo.save_run("a", self.player_id, self.result)
        other = self.repo.save_player("Другой")
        self.result["difficulty"] = "Сложно"
        self.repo.save_run("b", other, self.result)
        self.assertEqual(len(self.repo.runs("Сложно")), 1)
        self.assertEqual(len(self.repo.runs(player_id=self.player_id)), 1)

    def test_cascade_and_no_reseed(self):
        self.repo.save_run("a", self.player_id, self.result)
        self.repo.delete_player(self.player_id)
        self.assertEqual(self.repo.runs(), [])
        self.repo.close()
        self.repo = Repository(self.path)
        self.assertEqual(self.repo.players(), [])

    def test_invalid_run_does_not_update_profile(self):
        self.result["score"] = -1
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.save_run("a", self.player_id, self.result)
        self.assertEqual(self.repo.player(self.player_id)["games"], 0)
        self.assertEqual(self.repo.runs(), [])

    def test_settings_and_scores_survive_restart(self):
        self.repo.save_settings({"volume": 15, "muted": True})
        self.repo.save_run("a", self.player_id, self.result)
        self.repo.close()
        self.repo = Repository(self.path)
        self.assertEqual(self.repo.setting("volume"), 15)
        self.assertTrue(self.repo.setting("muted"))
        self.assertEqual(self.repo.runs()[0]["score"], 250)

    def test_name_sql_is_literal(self):
        name = "'); DROP TABLE runs; --"
        player_id = self.repo.save_player(name)
        self.assertEqual(self.repo.player(player_id)["name"], name)
        self.assertEqual(self.repo.runs(), [])


if __name__ == "__main__":
    unittest.main()
