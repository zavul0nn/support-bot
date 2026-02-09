from __future__ import annotations

import json
from typing import Any, Dict, Optional

from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder, KeyBuilder, StorageKey
from aiogram.fsm.state import State

from app.bot.utils.sqlite import SQLiteDatabase


class SQLiteFSMStorage(BaseStorage):
    """
    Persist FSM state/data in SQLite.
    """

    def __init__(self, db: SQLiteDatabase, *, key_builder: KeyBuilder | None = None) -> None:
        self.db = db
        self.key_builder = key_builder or DefaultKeyBuilder(
            with_bot_id=True,
            with_business_connection_id=True,
            with_destiny=True,
        )

    def _build_key(self, key: StorageKey) -> str:
        return self.key_builder.build(key)

    async def _get_record(self, storage_key: str) -> tuple[Optional[str], Dict[str, Any]]:
        async with self.db.conn.execute(
            "SELECT state, data FROM fsm WHERE key = ?",
            (storage_key,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None, {}
        raw = row["data"]
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        return row["state"], data

    async def _maybe_cleanup(self, storage_key: str, state: Optional[str], data: Dict[str, Any]) -> bool:
        if state is None and not data:
            await self.db.conn.execute("DELETE FROM fsm WHERE key = ?", (storage_key,))
            await self.db.conn.commit()
            return True
        return False

    async def close(self) -> None:  # pragma: no cover
        # Connection is owned by SQLiteDatabase and closed elsewhere.
        return None

    async def set_state(self, key: StorageKey, state: Any = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        storage_key = self._build_key(key)
        _, current_data = await self._get_record(storage_key)
        if await self._maybe_cleanup(storage_key, state_value, current_data):
            return
        await self.db.conn.execute(
            """
            INSERT INTO fsm (key, state, data)
            VALUES (?, ?, '{}')
            ON CONFLICT(key) DO UPDATE SET state = excluded.state
            """,
            (storage_key, state_value),
        )
        await self.db.conn.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        storage_key = self._build_key(key)
        async with self.db.conn.execute(
            "SELECT state FROM fsm WHERE key = ?",
            (storage_key,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return row["state"]

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        storage_key = self._build_key(key)
        current_state, _ = await self._get_record(storage_key)
        payload_data = data or {}
        if await self._maybe_cleanup(storage_key, current_state, payload_data):
            return
        payload = json.dumps(payload_data, ensure_ascii=False)
        await self.db.conn.execute(
            """
            INSERT INTO fsm (key, state, data)
            VALUES (?, NULL, ?)
            ON CONFLICT(key) DO UPDATE SET data = excluded.data
            """,
            (storage_key, payload),
        )
        await self.db.conn.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        storage_key = self._build_key(key)
        async with self.db.conn.execute(
            "SELECT data FROM fsm WHERE key = ?",
            (storage_key,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None or row["data"] in (None, ""):
            return {}
        try:
            return json.loads(row["data"])
        except json.JSONDecodeError:
            return {}
