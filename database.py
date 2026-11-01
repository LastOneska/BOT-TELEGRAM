from contextlib import contextmanager
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    city TEXT NOT NULL DEFAULT 'Bandung',
                    alerts_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS areas (
                    city TEXT NOT NULL,
                    osm_type TEXT NOT NULL,
                    osm_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (city, osm_type, osm_id)
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    distance_km REAL NOT NULL,
                    price INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS orders_user_created
                    ON orders(user_id, created_at);
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    telegram_message_id INTEGER NOT NULL,
                    vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, telegram_message_id)
                );
                """
            )

    def ensure_user(self, user_id: int, username: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users (user_id, username, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
                """,
                (user_id, username, now),
            )

    def set_alerts(self, user_id: int, enabled: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE users SET alerts_enabled = ? WHERE user_id = ?",
                (int(enabled), user_id),
            )

    def get_alert_users(self) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT user_id FROM users WHERE alerts_enabled = 1"
            ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def replace_areas(self, city: str, areas: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute("DELETE FROM areas WHERE city = ?", (city,))
            connection.executemany(
                """
                INSERT INTO areas
                    (city, osm_type, osm_id, name, category, latitude, longitude, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        city,
                        area["osm_type"],
                        area["osm_id"],
                        area["name"],
                        area["category"],
                        area["latitude"],
                        area["longitude"],
                        now,
                    )
                    for area in areas
                ],
            )

    def get_areas(self, city: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT osm_type, osm_id, name, category, latitude, longitude, updated_at
                FROM areas WHERE city = ? ORDER BY name
                """,
                (city,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_order(self, user_id: int, distance_km: float, price: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO orders (user_id, distance_km, price, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, distance_km, price, datetime.now(timezone.utc).isoformat()),
            )

    def get_orders(
        self, user_id: int, start_utc: datetime, end_utc: datetime
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT distance_km, price, created_at
                FROM orders
                WHERE user_id = ? AND created_at >= ? AND created_at < ?
                ORDER BY created_at
                """,
                (
                    user_id,
                    start_utc.astimezone(timezone.utc).isoformat(),
                    end_utc.astimezone(timezone.utc).isoformat(),
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_feedback(self, user_id: int, message_id: int, vote: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO feedback
                    (user_id, telegram_message_id, vote, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    message_id,
                    vote,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return cursor.rowcount == 1
