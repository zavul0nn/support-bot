import asyncio
import logging
from datetime import datetime, timezone

import re
from contextlib import suppress

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hlink
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.manager import Manager
from app.bot.types.album import Album
from app.bot.utils.create_forum_topic import (
    create_forum_topic,
    get_or_create_forum_topic,
)
from app.bot.handlers.group.panel import panel_text, main_keyboard
from app.bot.utils.business_hours import MOSCOW_TZ, is_within_business_hours
from app.bot.utils.redis import RedisStorage, FAQStorage, SettingsStorage
from app.bot.utils.redis.models import UserData
from app.bot.utils.reminders import schedule_support_reminder
from app.bot.utils.security import (
    SuspicionResult,
    analyze_user_message,
    sanitize_display_name,
)

TOPIC_ICON_RESTORE_DELAY = 3.0

GRATITUDE_PHRASES = {
    'спасибо',
    'спасибо большое',
    'спасибо за помощь',
    'благодарю',
    'thank you',
    'thanks',
    'thx',
}


router = Router()
router.message.filter(F.chat.type == "private", StateFilter(None))

logger = logging.getLogger(__name__)


def entities_contain_links(msg: Message) -> bool:
    for container in (msg.entities or [], msg.caption_entities or []):
        for entity in container:
            if entity.type in {"url", "text_link"}:
                return True
    return False


def _was_previous_user_message_outside_hours(
    user_data: UserData,
    *,
    hours_start,
    hours_end,
) -> bool:
    if user_data.last_user_message_at is None:
        return False

    try:
        previous_message_at = datetime.fromisoformat(user_data.last_user_message_at)
    except ValueError:
        return False

    return not is_within_business_hours(
        previous_message_at,
        start=hours_start,
        end=hours_end,
        tz=MOSCOW_TZ,
    )


@router.edited_message()
async def handle_edited_message(message: Message, manager: Manager) -> None:
    """
    Handle edited messages.

    :param message: The edited message.
    :param manager: Manager object.
    :return: None
    """
    # Get the text for the edited message
    text = manager.text_message.get("message_edited")
    # Reply with a short-lived confirmation
    msg = await message.reply(text)
    Manager.schedule_message_cleanup(msg)


@router.message(F.media_group_id)
@router.message(F.media_group_id.is_(None))
async def handle_incoming_message(
        message: Message,
        manager: Manager,
        redis: RedisStorage,
        user_data: UserData,
        apscheduler: AsyncIOScheduler,
        faq: FAQStorage,
        settings: SettingsStorage,
        album: Album | None = None,
) -> None:
    """
    Handles incoming messages and copies them to the forum topic.
    If the user is banned, the messages are ignored.

    :param message: The incoming message.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param user_data: UserData object.
    :param album: Album object or None.
    :return: None
    """
    # Check if the user is banned
    if user_data.is_banned:
        return

    text_content = message.text or message.caption or ""

    if manager.config.security_enabled:
        suspicion = analyze_user_message(
            full_name=user_data.full_name,
            username=user_data.username,
            message_text=text_content,
            entities_contains_link=entities_contain_links(message),
        )
    else:
        suspicion = SuspicionResult(high=[], medium=[])

    if suspicion.should_block:
        user_data.is_banned = True
        user_data.awaiting_reply = False
        await redis.update_user(user_data.id, user_data)

        reason_text = "; ".join(suspicion.reasons())
        logger.warning(
            "Auto-ban triggered for user %s (%s). Reasons: %s. Original message: %r",
            user_data.id,
            user_data.username,
            reason_text,
            text_content,
        )
        await message.reply(
            manager.text_message.get("auto_blocked_notice").format(reason=reason_text),
        )

        thread_id = user_data.message_thread_id
        group_kwargs = {"message_thread_id": thread_id} if thread_id is not None else {}
        safe_name = sanitize_display_name(user_data.full_name, placeholder=f"User {user_data.id}")
        await message.bot.send_message(
            chat_id=manager.config.bot.GROUP_ID,
            text=manager.text_message.get("auto_blocked_alert").format(
                user=hlink(safe_name, f"tg://user?id={user_data.id}"),
                reason=reason_text,
            ),
            disable_web_page_preview=True,
            **group_kwargs,
        )
        return

    ticket_was_resolved = user_data.ticket_status == "resolved"
    if ticket_was_resolved:
        user_data.operator_replied = False
    should_reset_icon = ticket_was_resolved or not user_data.operator_replied

    async def copy_message_to_topic() -> int | None:
        """
        Copies the message or album to the forum topic.
        If no album is provided, the message is copied. Otherwise, the album is copied.
        """
        message_thread_id = await get_or_create_forum_topic(
            message.bot,
            redis,
            manager.config,
            user_data,
        )

        if not album:
            await message.forward(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=message_thread_id,
            )
        else:
            await album.copy_to(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=message_thread_id,
            )
        return message_thread_id

    try:
        thread_id = await copy_message_to_topic()
    except TelegramBadRequest as ex:
        if "message thread not found" in ex.message:
            user_data.message_thread_id = await create_forum_topic(
                message.bot,
                manager.config,
                user_data.full_name,
            )
            await redis.update_user(user_data.id, user_data)
            thread_id = await copy_message_to_topic()
        else:
            raise

    if thread_id is not None and should_reset_icon:
        with suppress(TelegramBadRequest):
            await message.bot.edit_forum_topic(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=thread_id,
                icon_custom_emoji_id=manager.config.bot.BOT_EMOJI_ID,
            )
        if user_data.panel_message_id:
            with suppress(TelegramBadRequest):
                await message.bot.delete_message(
                    chat_id=manager.config.bot.GROUP_ID,
                    message_id=user_data.panel_message_id,
                )
        panel_message = await message.bot.send_message(
            chat_id=manager.config.bot.GROUP_ID,
            message_thread_id=thread_id,
            text=panel_text(manager.text_message, user_data),
            reply_markup=main_keyboard(
                user_data.id,
                ticket_status=user_data.ticket_status,
            ),
        )
        user_data.panel_message_id = panel_message.message_id

    should_send_confirmation = (
        user_data.last_user_message_at is None
        or ticket_was_resolved
    )
    outside_hours_notice_text: str | None = None
    hours = await settings.get_business_hours()
    if hours.enabled and not is_within_business_hours(
        datetime.now(MOSCOW_TZ),
        start=hours.start,
        end=hours.end,
        tz=MOSCOW_TZ,
    ):
        previous_was_outside = _was_previous_user_message_outside_hours(
            user_data,
            hours_start=hours.start,
            hours_end=hours.end,
        )
        if should_send_confirmation or not previous_was_outside:
            language_code = manager.text_message.language_code
            outside_hours_notice_text = (
                await settings.get_business_hours_message(language_code)
                or manager.text_message.get("outside_business_hours")
            )

    if should_send_confirmation:
        # Уведомляем пользователя только на старте диалога или после повторного открытия тикета
        text = manager.text_message.get("message_sent")
        msg = await message.reply(text)
        Manager.schedule_message_cleanup(msg)

        if outside_hours_notice_text:
            await manager.send_message(outside_hours_notice_text, replace_previous=False)

        if await faq.has_items():
            suggestion_text = manager.text_message.get("faq_suggestion")
            builder = InlineKeyboardBuilder()
            builder.button(text="📚 Часто задаваемые вопросы", callback_data="faq:open")
            builder.adjust(1)
            await manager.send_message(
                suggestion_text,
                reply_markup=builder.as_markup(),
                disable_web_page_preview=True,
            )
    elif outside_hours_notice_text:
        await manager.send_message(outside_hours_notice_text, replace_previous=False)

    normalized = re.sub(r'[\W_]+', ' ', text_content.lower()).strip()
    if user_data.ticket_status == "resolved" and normalized in GRATITUDE_PHRASES:
        user_data.awaiting_reply = False
        await redis.update_user(user_data.id, user_data)
        return

    user_data.ticket_status = "open"
    user_data.awaiting_reply = True
    user_data.last_user_message_at = datetime.now(timezone.utc).isoformat()
    await redis.update_user(user_data.id, user_data)

    if ticket_was_resolved and user_data.message_thread_id is not None:
        thread_id = user_data.message_thread_id
        group_id = manager.config.bot.GROUP_ID
        bot = message.bot
        icon_id = manager.config.bot.BOT_EMOJI_ID

        async def restore_topic_icon() -> None:
            await asyncio.sleep(TOPIC_ICON_RESTORE_DELAY)
            with suppress(TelegramBadRequest):
                await bot.edit_forum_topic(
                    chat_id=group_id,
                    message_thread_id=thread_id,
                    icon_custom_emoji_id=icon_id,
                )

        asyncio.create_task(restore_topic_icon())

    if manager.config.bot.REMINDERS_ENABLED:
        schedule_support_reminder(
            apscheduler,
            bot_token=manager.config.bot.TOKEN,
            group_id=manager.config.bot.GROUP_ID,
            user_id=user_data.id,
            message_thread_id=user_data.message_thread_id,
            language_code=user_data.language_code,
            db_path=manager.config.sqlite.PATH,
            proxy_url=manager.config.bot.PROXY_URL,
        )
