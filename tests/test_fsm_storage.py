import pytest

from aiogram.fsm.storage.base import StorageKey

from app.bot.utils.fsm_storage import SQLiteFSMStorage
from app.bot.utils.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_fsm_storage_cleanup(tmp_path):
    db_path = tmp_path / "fsm.sqlite3"
    db = SQLiteDatabase(path=db_path)
    await db.connect()
    storage = SQLiteFSMStorage(db)
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)

    await storage.set_state(key, "step1")
    await storage.set_data(key, {"value": 1})

    async with db.conn.execute("SELECT COUNT(*) AS cnt FROM fsm") as cursor:
        row = await cursor.fetchone()
    assert row["cnt"] == 1

    await storage.set_state(key, None)
    async with db.conn.execute("SELECT COUNT(*) AS cnt FROM fsm") as cursor:
        row = await cursor.fetchone()
    assert row["cnt"] == 1

    await storage.set_data(key, {})
    async with db.conn.execute("SELECT COUNT(*) AS cnt FROM fsm") as cursor:
        row = await cursor.fetchone()
    assert row["cnt"] == 0

    await db.close()
