import pytest

from app.bot.utils.business_hours import parse_hhmm
from app.bot.utils.redis.settings import SettingsStorage
from app.bot.utils.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_get_all_greetings_filters_only_prefixed_keys(tmp_path) -> None:
    db = SQLiteDatabase(path=tmp_path / "settings.sqlite3")
    await db.connect()
    storage = SettingsStorage(db)

    await storage.set_greeting("en", "Hello!")
    await storage.set_greeting("ru", "Привет!")
    await db.conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        ("unrelated", "should be ignored"),
    )
    await db.conn.commit()

    result = await storage.get_all_greetings()

    assert result == {"en": "Hello!", "ru": "Привет!"}
    await db.close()


@pytest.mark.asyncio
async def test_set_get_and_reset_roundtrip(tmp_path) -> None:
    db = SQLiteDatabase(path=tmp_path / "settings.sqlite3")
    await db.connect()
    storage = SettingsStorage(db)

    assert await storage.get_greeting("en") is None

    await storage.set_greeting("en", "Hello {full_name}")
    assert await storage.get_greeting("en") == "Hello {full_name}"

    await storage.reset_greeting("en")
    assert await storage.get_greeting("en") is None
    await db.close()


@pytest.mark.asyncio
async def test_get_all_resolved_filters_only_prefixed_keys(tmp_path) -> None:
    db = SQLiteDatabase(path=tmp_path / "settings.sqlite3")
    await db.connect()
    storage = SettingsStorage(db)

    await storage.set_resolved_message("en", "Thanks!")
    await storage.set_resolved_message("ru", "Спасибо!")
    await storage.set_greeting("en", "ignored for resolved")

    result = await storage.get_all_resolved_messages()

    assert result == {"en": "Thanks!", "ru": "Спасибо!"}
    await db.close()


@pytest.mark.asyncio
async def test_resolved_message_roundtrip(tmp_path) -> None:
    db = SQLiteDatabase(path=tmp_path / "settings.sqlite3")
    await db.connect()
    storage = SettingsStorage(db)

    assert await storage.get_resolved_message("en") is None

    await storage.set_resolved_message("en", "Bye!")
    assert await storage.get_resolved_message("en") == "Bye!"

    await storage.reset_resolved_message("en")
    assert await storage.get_resolved_message("en") is None
    await db.close()


@pytest.mark.asyncio
async def test_business_hours_defaults_and_range_roundtrip(tmp_path) -> None:
    db = SQLiteDatabase(path=tmp_path / "settings.sqlite3")
    await db.connect()
    storage = SettingsStorage(db)

    hours = await storage.get_business_hours()
    assert hours.enabled is True
    assert hours.start == parse_hhmm("09:00")
    assert hours.end == parse_hhmm("00:00")

    await storage.set_business_hours_enabled(True)
    await storage.set_business_hours_range(parse_hhmm("10:30"), parse_hhmm("22:15"))

    hours = await storage.get_business_hours()
    assert hours.enabled is True
    assert hours.start == parse_hhmm("10:30")
    assert hours.end == parse_hhmm("22:15")

    await storage.set_business_hours_enabled(False)
    hours = await storage.get_business_hours()
    assert hours.enabled is False
    await db.close()


@pytest.mark.asyncio
async def test_business_hours_message_roundtrip(tmp_path) -> None:
    db = SQLiteDatabase(path=tmp_path / "settings.sqlite3")
    await db.connect()
    storage = SettingsStorage(db)

    assert await storage.get_business_hours_message("ru") is None

    await storage.set_business_hours_message("ru", "Мы сейчас не работаем")
    assert await storage.get_business_hours_message("ru") == "Мы сейчас не работаем"
    assert await storage.get_all_business_hours_messages() == {"ru": "Мы сейчас не работаем"}

    await storage.reset_business_hours_message("ru")
    assert await storage.get_business_hours_message("ru") is None
    await db.close()
