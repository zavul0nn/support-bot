from __future__ import annotations

from app.bot.utils.sqlite import SQLiteDatabase


class SettingsStorage:
    """Storage for bot-wide settings."""

    NAME = "settings"
    GREETING_PREFIX = "greeting:"
    RESOLVED_PREFIX = "resolved_message:"

    def __init__(self, db: SQLiteDatabase) -> None:
        """Initialize storage with a SQLite database."""
        self.db = db

    async def _collect_prefixed(self, prefix: str) -> dict[str, str]:
        """Return a mapping filtered by a prefix."""
        async with self.db.conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE ?",
            (f"{prefix}%",),
        ) as cursor:
            rows = await cursor.fetchall()

        result: dict[str, str] = {}
        for row in rows:
            key = row["key"]
            if not key.startswith(prefix):
                continue
            language = key[len(prefix):]
            result[language] = row["value"]

        return result

    async def _get_prefixed_value(self, prefix: str, language: str) -> str | None:
        """Return a stored value for the language if present."""
        async with self.db.conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (f"{prefix}{language}",),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return row["value"]

    async def _set_prefixed_value(self, prefix: str, language: str, text: str) -> None:
        """Persist a value for the language."""
        await self.db.conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (f"{prefix}{language}", text),
        )
        await self.db.conn.commit()

    async def _reset_prefixed_value(self, prefix: str, language: str) -> None:
        """Remove a value for the language if it exists."""
        await self.db.conn.execute(
            "DELETE FROM settings WHERE key = ?",
            (f"{prefix}{language}",),
        )
        await self.db.conn.commit()

    async def get_all_greetings(self) -> dict[str, str]:
        """Return greetings overrides indexed by language."""
        return await self._collect_prefixed(self.GREETING_PREFIX)

    async def get_greeting(self, language: str) -> str | None:
        """Return greeting override for the language if present."""
        return await self._get_prefixed_value(self.GREETING_PREFIX, language)

    async def set_greeting(self, language: str, text: str) -> None:
        """Persist greeting override for the language."""
        await self._set_prefixed_value(self.GREETING_PREFIX, language, text)

    async def reset_greeting(self, language: str) -> None:
        """Remove greeting override for the language if it exists."""
        await self._reset_prefixed_value(self.GREETING_PREFIX, language)

    async def get_all_resolved_messages(self) -> dict[str, str]:
        """Return ticket resolution overrides indexed by language."""
        return await self._collect_prefixed(self.RESOLVED_PREFIX)

    async def get_resolved_message(self, language: str) -> str | None:
        """Return ticket resolution override for the language if present."""
        return await self._get_prefixed_value(self.RESOLVED_PREFIX, language)

    async def set_resolved_message(self, language: str, text: str) -> None:
        """Persist ticket resolution override for the language."""
        await self._set_prefixed_value(self.RESOLVED_PREFIX, language, text)

    async def reset_resolved_message(self, language: str) -> None:
        """Remove ticket resolution override for the language if it exists."""
        await self._reset_prefixed_value(self.RESOLVED_PREFIX, language)
