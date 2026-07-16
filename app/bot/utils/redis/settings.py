from __future__ import annotations

from datetime import time

from app.bot.utils.business_hours import (
    BusinessHours,
    format_hhmm,
    parse_hhmm,
)
from app.bot.utils.sqlite import SQLiteDatabase


class SettingsStorage:
    """Storage for bot-wide settings."""

    NAME = "settings"
    GREETING_PREFIX = "greeting:"
    RESOLVED_PREFIX = "resolved_message:"
    BUSINESS_HOURS_ENABLED_KEY = "business_hours:enabled"
    BUSINESS_HOURS_START_KEY = "business_hours:start"
    BUSINESS_HOURS_END_KEY = "business_hours:end"
    BUSINESS_HOURS_MESSAGE_PREFIX = "business_hours_message:"

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

    async def _get_value(self, key: str) -> str | None:
        """Return a raw setting value."""
        async with self.db.conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return row["value"]

    async def _set_value(self, key: str, value: str) -> None:
        """Persist a raw setting value."""
        await self.db.conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.db.conn.commit()

    async def get_business_hours(self) -> BusinessHours:
        """Return configured business hours."""
        enabled = await self._get_value(self.BUSINESS_HOURS_ENABLED_KEY)
        start = await self._get_value(self.BUSINESS_HOURS_START_KEY)
        end = await self._get_value(self.BUSINESS_HOURS_END_KEY)

        return BusinessHours(
            enabled=enabled != "0",
            start=parse_hhmm(start) if start else BusinessHours().start,
            end=parse_hhmm(end) if end else BusinessHours().end,
        )

    async def set_business_hours_enabled(self, enabled: bool) -> None:
        """Enable or disable business-hours notices."""
        await self._set_value(self.BUSINESS_HOURS_ENABLED_KEY, "1" if enabled else "0")

    async def set_business_hours_range(self, start: time, end: time) -> None:
        """Persist business-hours interval."""
        await self._set_value(self.BUSINESS_HOURS_START_KEY, format_hhmm(start))
        await self._set_value(self.BUSINESS_HOURS_END_KEY, format_hhmm(end))

    async def get_all_business_hours_messages(self) -> dict[str, str]:
        """Return out-of-hours message overrides indexed by language."""
        return await self._collect_prefixed(self.BUSINESS_HOURS_MESSAGE_PREFIX)

    async def get_business_hours_message(self, language: str) -> str | None:
        """Return out-of-hours message override for the language if present."""
        return await self._get_prefixed_value(self.BUSINESS_HOURS_MESSAGE_PREFIX, language)

    async def set_business_hours_message(self, language: str, text: str) -> None:
        """Persist out-of-hours message override for the language."""
        await self._set_prefixed_value(self.BUSINESS_HOURS_MESSAGE_PREFIX, language, text)

    async def reset_business_hours_message(self, language: str) -> None:
        """Remove out-of-hours message override for the language if it exists."""
        await self._reset_prefixed_value(self.BUSINESS_HOURS_MESSAGE_PREFIX, language)
