from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.markdown import hlink
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.utils.redis import RedisStorage
from app.bot.utils.sqlite import SQLiteDatabase
from app.bot.utils.security import sanitize_display_name
from app.bot.utils.texts import TextMessage

REMINDER_DELAY_SECONDS = 5 * 60
_REMINDER_JOB_PREFIX = "ticket_reminder_"


def _job_id(user_id: int) -> str:
    return f"{_REMINDER_JOB_PREFIX}{user_id}"


async def send_support_reminder(
    *,
    bot_token: str,
    group_id: int,
    user_id: int,
    message_thread_id: int,
    language_code: str | None,
    db_path: str,
) -> None:
    db = SQLiteDatabase(path=Path(db_path))
    await db.connect()
    storage = RedisStorage(db)
    try:
        user_data = await storage.get_user(user_id)
        if not user_data or not user_data.awaiting_reply or user_data.ticket_status != "open":
            return

        language = language_code or user_data.language_code or "en"
        text_template = TextMessage(language).get("support_reminder")
        safe_name = sanitize_display_name(user_data.full_name, placeholder=f"User {user_data.id}")
        user_link = hlink(safe_name, f"tg://user?id={user_data.id}")
        text = text_template.format(user=user_link)

        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        try:
            await bot.send_message(
                chat_id=group_id,
                text=text,
                message_thread_id=message_thread_id,
            )
        finally:
            await bot.session.close()
    finally:
        await db.close()


def schedule_support_reminder(
    scheduler: AsyncIOScheduler,
    *,
    bot_token: str,
    group_id: int,
    user_id: int,
    message_thread_id: int | None,
    language_code: str | None,
    db_path: str,
) -> None:
    if message_thread_id is None:
        return

    resolved_db_path = str(Path(db_path).resolve())
    run_at = datetime.now(timezone.utc) + timedelta(seconds=REMINDER_DELAY_SECONDS)
    scheduler.add_job(
        send_support_reminder,
        trigger="date",
        run_date=run_at,
        id=_job_id(user_id),
        replace_existing=True,
        kwargs={
            "bot_token": bot_token,
            "group_id": group_id,
            "user_id": user_id,
            "message_thread_id": message_thread_id,
            "language_code": language_code,
            "db_path": resolved_db_path,
        },
        misfire_grace_time=60,
    )


def cancel_support_reminder(scheduler: AsyncIOScheduler, user_id: int) -> None:
    try:
        scheduler.remove_job(_job_id(user_id))
    except JobLookupError:
        pass
