from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import stat
from pathlib import Path
from typing import Any

import aiosqlite


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    message_thread_id INTEGER,
    message_silent_id INTEGER,
    message_silent_mode INTEGER NOT NULL DEFAULT 0,
    full_name TEXT NOT NULL,
    username TEXT,
    state TEXT NOT NULL,
    is_banned INTEGER NOT NULL DEFAULT 0,
    language_code TEXT,
    ticket_status TEXT NOT NULL,
    awaiting_reply INTEGER NOT NULL DEFAULT 0,
    last_user_message_at TEXT,
    created_at TEXT NOT NULL,
    panel_message_id INTEGER,
    operator_replied INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_users_message_thread_id
    ON users(message_thread_id);
CREATE INDEX IF NOT EXISTS idx_users_is_banned
    ON users(is_banned);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS faq_items (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_faq_items_sort_order
    ON faq_items(sort_order);

CREATE TABLE IF NOT EXISTS fsm (
    key TEXT PRIMARY KEY,
    state TEXT,
    data TEXT
);
"""

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class SQLiteDatabase:
    path: Path | str
    _conn: aiosqlite.Connection | None = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = False
        if not self.path.exists():
            self.path.touch()
            created = True
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        if created:
            self._ensure_permissions()

    def _ensure_permissions(self) -> None:
        if os.name == "nt":
            return

        try:
            os.chmod(self.path, 0o664)
        except OSError as exc:
            logger.warning("Failed to chmod SQLite DB file %s: %s", self.path, exc)
            return

        try:
            mode = stat.S_IMODE(self.path.stat().st_mode)
        except OSError as exc:
            logger.warning("Failed to stat SQLite DB file %s: %s", self.path, exc)
            return

        if mode & 0o666 != 0o664:
            logger.warning(
                "SQLite DB permissions not applied: %s has mode %o",
                self.path,
                mode,
            )

        try:
            st = self.path.stat()
            uid = getattr(os, "geteuid", None)
            gid = getattr(os, "getegid", None)
            if callable(uid) and st.st_uid != uid():
                logger.warning(
                    "SQLite DB owner mismatch: %s uid=%s (process uid=%s)",
                    self.path,
                    st.st_uid,
                    uid(),
                )
            if callable(gid) and st.st_gid != gid():
                logger.warning(
                    "SQLite DB group mismatch: %s gid=%s (process gid=%s)",
                    self.path,
                    st.st_gid,
                    gid(),
                )
        except OSError as exc:
            logger.warning("Failed to stat SQLite DB file owner for %s: %s", self.path, exc)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SQLite connection is not initialized.")
        return self._conn

    async def get_meta(self, key: str) -> str | None:
        async with self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return str(row["value"])

    async def set_meta(self, key: str, value: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.conn.commit()

    async def has_any_data(self) -> bool:
        for table in ("users", "settings", "faq_items"):
            async with self.conn.execute(f"SELECT 1 FROM {table} LIMIT 1") as cursor:
                row = await cursor.fetchone()
            if row is not None:
                return True
        return False

    async def executemany(self, query: str, params: list[tuple[Any, ...]]) -> None:
        if not params:
            return
        await self.conn.executemany(query, params)
        await self.conn.commit()
