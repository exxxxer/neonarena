"""SQLite profiles, run history and persistent settings."""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

from .engine import DIFFICULTIES

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def resource(relative):
    return ROOT / relative


def data_dir():
    override = os.environ.get("NEONARENA_DATA_DIR")
    path = (
        Path(override)
        if override
        else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS players(
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE,
                best_score INTEGER NOT NULL DEFAULT 0,
                games INTEGER NOT NULL DEFAULT 0,
                total_kills INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS runs(
                id INTEGER PRIMARY KEY, run_key TEXT NOT NULL UNIQUE,
                player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                score INTEGER NOT NULL CHECK(score>=0),
                wave INTEGER NOT NULL CHECK(wave>=1),
                kills INTEGER NOT NULL CHECK(kills>=0),
                duration REAL NOT NULL CHECK(duration>=0),
                difficulty TEXT NOT NULL,
                completed INTEGER NOT NULL CHECK(completed IN(0,1)),
                upgrades TEXT NOT NULL, played_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS runs_player ON runs(player_id);
            CREATE INDEX IF NOT EXISTS runs_score ON runs(completed,score DESC);
        """)
        initialized = self.connection.execute(
            "SELECT value FROM settings WHERE key='initialized'"
        ).fetchone()
        if not initialized:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO players(name,name_key) VALUES(?,?)", ("Игрок", "игрок")
                )
                self.connection.execute(
                    "INSERT INTO settings(key,value) VALUES('initialized','true')"
                )

    def players(self):
        return [dict(row) for row in self.connection.execute("SELECT * FROM players ORDER BY id")]

    def player(self, player_id):
        row = self.connection.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
        return dict(row) if row else None

    def save_player(self, name, player_id=None):
        name = name.strip()
        if not 1 <= len(name) <= 24:
            raise ValueError("Имя должно содержать от 1 до 24 символов.")
        try:
            with self.connection:
                if player_id is None:
                    cursor = self.connection.execute(
                        "INSERT INTO players(name,name_key) VALUES(?,?)", (name, name.casefold())
                    )
                    return cursor.lastrowid
                if not self.player(player_id):
                    raise ValueError("Игрок не найден.")
                self.connection.execute(
                    "UPDATE players SET name=?, name_key=? WHERE id=?",
                    (name, name.casefold(), player_id),
                )
                return player_id
        except sqlite3.IntegrityError as error:
            raise ValueError("Игрок с таким именем уже существует.") from error

    def delete_player(self, player_id):
        with self.connection:
            self.connection.execute("DELETE FROM players WHERE id=?", (player_id,))

    def save_run(self, run_key, player_id, result):
        if result["difficulty"] not in DIFFICULTIES:
            raise ValueError("Неизвестная сложность.")
        completed = int(result["completed"])
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO runs(run_key,player_id,score,wave,kills,duration,"
                "difficulty,completed,upgrades,played_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(run_key) DO NOTHING",
                (
                    run_key,
                    player_id,
                    result["score"],
                    result["wave"],
                    result["kills"],
                    result["duration"],
                    result["difficulty"],
                    completed,
                    json.dumps(result["upgrades"], ensure_ascii=False),
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            if cursor.rowcount:
                self.connection.execute(
                    "UPDATE players SET games=games+1,total_kills=total_kills+?,"
                    "best_score=MAX(best_score,?) WHERE id=?",
                    (result["kills"], result["score"] if completed else 0, player_id),
                )
        return cursor.rowcount == 1

    def runs(self, difficulty="Все", player_id=None, include_abandoned=False):
        sql = "SELECT r.*,p.name FROM runs r JOIN players p ON r.player_id=p.id WHERE 1=1"
        parameters = []
        if not include_abandoned:
            sql += " AND r.completed=1"
        if difficulty != "Все":
            sql += " AND r.difficulty=?"
            parameters.append(difficulty)
        if player_id is not None:
            sql += " AND r.player_id=?"
            parameters.append(player_id)
        sql += " ORDER BY r.score DESC,r.id DESC LIMIT 100"
        return [dict(row) for row in self.connection.execute(sql, parameters)]

    def setting(self, key, default=None):
        row = self.connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        try:
            return json.loads(row["value"]) if row else default
        except json.JSONDecodeError:
            return default

    def save_settings(self, values):
        with self.connection:
            self.connection.executemany(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()],
            )

    def close(self):
        self.connection.close()
