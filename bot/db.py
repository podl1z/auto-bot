"""Слой доступа к SQLite. Схема создаётся сама при первом запуске."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS memes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         TEXT    NOT NULL,
    file_unique_id  TEXT    NOT NULL UNIQUE,
    kind            TEXT    NOT NULL,
    caption         TEXT,
    added_by        INTEGER,
    added_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    broken          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS triggers (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS greet_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    meme_id  INTEGER,
    ts       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_greet_lookup ON greet_log (chat_id, user_id, ts);

CREATE TABLE IF NOT EXISTS last_meme (
    chat_id  INTEGER PRIMARY KEY,
    meme_id  INTEGER NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "greeting_text": "Привет, {name}! 👋",
    "enabled": "1",
    "cooldown_minutes": "360",
}

DEFAULT_TRIGGERS = ["старт", "start", "привет"]


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() не был вызван")
        return self._conn

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        for phrase in DEFAULT_TRIGGERS:
            await self._conn.execute(
                "INSERT OR IGNORE INTO triggers (phrase) VALUES (?)", (phrase,)
            )
        await self._conn.commit()
        logger.info("База готова: %s", self._path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # --- настройки ---------------------------------------------------------

    async def get_setting(self, key: str) -> str:
        async with self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else DEFAULT_SETTINGS[key]

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()

    async def is_enabled(self) -> bool:
        return await self.get_setting("enabled") == "1"

    async def set_enabled(self, value: bool) -> None:
        await self.set_setting("enabled", "1" if value else "0")

    async def greeting_text(self) -> str:
        return await self.get_setting("greeting_text")

    async def cooldown_minutes(self) -> int:
        try:
            return int(await self.get_setting("cooldown_minutes"))
        except ValueError:
            return int(DEFAULT_SETTINGS["cooldown_minutes"])

    # --- мемы --------------------------------------------------------------

    async def add_meme(
        self,
        file_id: str,
        file_unique_id: str,
        kind: str,
        caption: str | None,
        added_by: int | None,
    ) -> int | None:
        """Возвращает id нового мема, либо None если такой уже есть."""
        try:
            cur = await self.conn.execute(
                "INSERT INTO memes (file_id, file_unique_id, kind, caption, added_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (file_id, file_unique_id, kind, caption, added_by),
            )
        except aiosqlite.IntegrityError:
            return None
        await self.conn.commit()
        return cur.lastrowid

    async def delete_meme(self, meme_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM memes WHERE id = ?", (meme_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def mark_broken(self, meme_id: int) -> None:
        await self.conn.execute("UPDATE memes SET broken = 1 WHERE id = ?", (meme_id,))
        await self.conn.commit()

    async def count_memes(self, only_alive: bool = True) -> int:
        sql = "SELECT COUNT(*) AS n FROM memes"
        if only_alive:
            sql += " WHERE broken = 0"
        async with self.conn.execute(sql) as cur:
            row = await cur.fetchone()
        return row["n"] if row else 0

    async def meme_at(self, offset: int) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM memes WHERE broken = 0 ORDER BY id LIMIT 1 OFFSET ?",
            (max(offset, 0),),
        ) as cur:
            return await cur.fetchone()

    async def pick_meme(self, chat_id: int) -> aiosqlite.Row | None:
        """Случайный живой мем, по возможности не тот же, что был в прошлый раз."""
        async with self.conn.execute(
            "SELECT * FROM memes WHERE broken = 0 AND id != "
            "COALESCE((SELECT meme_id FROM last_meme WHERE chat_id = ?), -1) "
            "ORDER BY RANDOM() LIMIT 1",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is not None:
            return row
        # в пуле остался ровно один мем — отдаём его же
        async with self.conn.execute(
            "SELECT * FROM memes WHERE broken = 0 ORDER BY RANDOM() LIMIT 1"
        ) as cur:
            return await cur.fetchone()

    async def set_last_meme(self, chat_id: int, meme_id: int) -> None:
        await self.conn.execute(
            "INSERT INTO last_meme (chat_id, meme_id) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET meme_id = excluded.meme_id",
            (chat_id, meme_id),
        )
        await self.conn.commit()

    # --- триггеры ----------------------------------------------------------

    async def list_triggers(self) -> list[str]:
        async with self.conn.execute(
            "SELECT phrase FROM triggers ORDER BY phrase"
        ) as cur:
            return [row["phrase"] for row in await cur.fetchall()]

    async def add_trigger(self, phrase: str) -> bool:
        try:
            await self.conn.execute(
                "INSERT INTO triggers (phrase) VALUES (?)", (phrase.strip().lower(),)
            )
        except aiosqlite.IntegrityError:
            return False
        await self.conn.commit()
        return True

    async def delete_trigger(self, phrase: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM triggers WHERE phrase = ?", (phrase.strip().lower(),)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # --- кулдаун и статистика ---------------------------------------------

    async def can_greet(self, chat_id: int, user_id: int, cooldown_minutes: int) -> bool:
        if cooldown_minutes <= 0:
            return True
        async with self.conn.execute(
            "SELECT 1 FROM greet_log WHERE chat_id = ? AND user_id = ? "
            "AND ts > datetime('now', ?) LIMIT 1",
            (chat_id, user_id, f"-{cooldown_minutes} minutes"),
        ) as cur:
            return await cur.fetchone() is None

    async def log_greet(self, chat_id: int, user_id: int, meme_id: int | None) -> None:
        await self.conn.execute(
            "INSERT INTO greet_log (chat_id, user_id, meme_id) VALUES (?, ?, ?)",
            (chat_id, user_id, meme_id),
        )
        await self.conn.commit()

    async def stats(self) -> dict[str, Any]:
        async def scalar(sql: str) -> int:
            async with self.conn.execute(sql) as cur:
                row = await cur.fetchone()
            return row[0] if row else 0

        return {
            "memes": await self.count_memes(),
            "broken": await scalar("SELECT COUNT(*) FROM memes WHERE broken = 1"),
            "triggers": await scalar("SELECT COUNT(*) FROM triggers"),
            "greets_total": await scalar("SELECT COUNT(*) FROM greet_log"),
            "greets_day": await scalar(
                "SELECT COUNT(*) FROM greet_log WHERE ts > datetime('now', '-1 day')"
            ),
            "chats": await scalar("SELECT COUNT(DISTINCT chat_id) FROM greet_log"),
            "users": await scalar("SELECT COUNT(DISTINCT user_id) FROM greet_log"),
        }
