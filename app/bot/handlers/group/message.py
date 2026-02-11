import asyncio
from contextlib import suppress
from typing import Optional

from aiogram import Router, F
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import MagicData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.markdown import hlink

from app.bot.manager import Manager
from app.bot.types.album import Album
from app.bot.utils.language import resolve_language_code
from app.bot.utils.redis import RedisStorage
from app.bot.utils.reminders import cancel_support_reminder
from app.bot.utils.security import sanitize_display_name
from app.bot.utils.texts import TextMessage

router = Router()
router.message.filter(
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
    F.chat.type.in_(["group", "supergroup"]),
    F.message_thread_id.is_not(None),
)


@router.message(F.forum_topic_created)
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    await asyncio.sleep(3)
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    # Generate a URL for the user's profile
    url = f"https://t.me/{user_data.username[1:]}" if user_data.username != "-" else f"tg://user?id={user_data.id}"

    # Get the appropriate text based on the user's state
    topic_language = resolve_language_code(user_data.language_code or manager.config.bot.DEFAULT_LANGUAGE)
    text = TextMessage(topic_language).get("user_started_bot")
    safe_name = sanitize_display_name(user_data.full_name, placeholder=f"User {user_data.id}")

    message = await message.bot.send_message(
        chat_id=manager.config.bot.GROUP_ID,
        text=text.format(name=hlink(safe_name, url)),
        message_thread_id=user_data.message_thread_id
    )

    # Pin the message
    await message.pin()


@router.message(F.pinned_message | F.forum_topic_edited | F.forum_topic_closed | F.forum_topic_reopened)
async def handler(message: Message) -> None:
    """
    Delete service messages such as pinned, edited, closed, or reopened forum topics.

    :param message: Message object.
    :return: None
    """
    await message.delete()


@router.message(F.media_group_id, F.from_user[F.is_bot.is_(False)])
@router.message(F.media_group_id.is_(None), F.from_user[F.is_bot.is_(False)])
async def handler(message: Message, manager: Manager, redis: RedisStorage, apscheduler: AsyncIOScheduler, album: Optional[Album] = None) -> None:
    """
    Handles user messages and sends them to the respective user.
    If silent mode is enabled for the user, the messages are ignored.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param album: Album object or None.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if message.text and message.text.strip().startswith("/"):
        return

    if user_data.message_silent_mode:
        # If silent mode is enabled, ignore all messages.
        return

    text = manager.text_message.get("message_sent_to_user")

    try:
        if not album:
            sent_message = await message.copy_to(chat_id=user_data.id)
            await redis.add_message_link(
                message.message_id,
                user_data.id,
                sent_message.message_id,
            )
        else:
            sent_messages = await album.copy_to(chat_id=user_data.id)
            for sent in sent_messages:
                await redis.add_message_link(
                    message.message_id,
                    user_data.id,
                    sent.message_id,
                )

    except TelegramAPIError as ex:
        if "blocked" in ex.message:
            text = manager.text_message.get("blocked_by_user")

    except (Exception,):
        text = manager.text_message.get("message_not_sent")

    # Reply with a short-lived confirmation
    msg = await message.reply(text)
    Manager.schedule_message_cleanup(msg)

    delete_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑", callback_data=f"delmsg:{message.message_id}")]
        ]
    )
    with suppress(TelegramBadRequest, TelegramAPIError):
        await message.reply("🗑", reply_markup=delete_markup)

    if user_data.ticket_status != "resolved" and not user_data.operator_replied:
        with suppress(TelegramBadRequest):
            await message.bot.edit_forum_topic(
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
                icon_custom_emoji_id=manager.config.bot.BOT_ACTIVE_EMOJI_ID,
            )
        user_data.operator_replied = True

    user_data.awaiting_reply = False
    await redis.update_user(user_data.id, user_data)
    cancel_support_reminder(
        apscheduler,
        user_data.id,
    )

