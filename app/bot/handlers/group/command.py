from contextlib import suppress
import html

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, MagicData
from aiogram.types import CallbackQuery, ForceReply, Message, InputMediaPhoto, InputMediaVideo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.utils.markdown import hcode, hbold

from app.bot.manager import Manager
from app.bot.handlers.group.panel import (
    PANEL_NAMESPACE,
    main_keyboard,
    panel_text,
    status_keyboard,
)
from app.bot.utils.language import resolve_language_code
from app.bot.utils.redis import RedisStorage, SettingsStorage, QuickReplyStorage, QuickReplyItem
from app.bot.utils.redis.models import UserData
from app.bot.utils.reminders import cancel_support_reminder, schedule_support_reminder
from app.bot.utils.remnawave import fetch_user_info, format_user_info, is_configured
from app.bot.utils.security import sanitize_display_name
from app.bot.utils.texts import TextMessage

router_id = Router()
router_id.message.filter(
    F.chat.type.in_(["group", "supergroup"]),
)


@router_id.message(Command("id"))
async def handler(message: Message) -> None:
    """
    Sends chat ID in response to the /id command.

    :param message: Message object.
    :return: None
    """
    await message.reply(hcode(message.chat.id))





async def _send_quick_reply(
    manager: Manager,
    item: QuickReplyItem,
    *,
    chat_id: int,
    message_thread_id: int | None = None,
) -> None:
    if item.text:
        await manager.bot.send_message(
            chat_id=chat_id,
            text=item.text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            message_thread_id=message_thread_id,
        )

    attachments = item.attachments
    media_group_types = {attachment.type for attachment in attachments}
    if attachments and media_group_types.issubset({"photo", "video"}) and len(attachments) > 1:
        media_group = []
        for attachment in attachments:
            if attachment.type == "photo":
                media = InputMediaPhoto(media=attachment.file_id)
            else:
                media = InputMediaVideo(media=attachment.file_id)
            if attachment.caption and not media_group:
                media.caption = attachment.caption
                media.parse_mode = "HTML"
            media_group.append(media)
        await manager.bot.send_media_group(
            chat_id=chat_id,
            media=media_group,
            message_thread_id=message_thread_id,
        )
        return

    for attachment in attachments:
        kwargs = {
            "chat_id": chat_id,
            "caption": attachment.caption,
            "parse_mode": "HTML",
            "message_thread_id": message_thread_id,
        }
        if attachment.caption is None:
            kwargs.pop("caption")
            kwargs.pop("parse_mode")

        if attachment.type == "photo":
            await manager.bot.send_photo(photo=attachment.file_id, **kwargs)
        elif attachment.type == "video":
            await manager.bot.send_video(video=attachment.file_id, **kwargs)
        elif attachment.type == "document":
            await manager.bot.send_document(document=attachment.file_id, **kwargs)
        elif attachment.type == "animation":
            await manager.bot.send_animation(animation=attachment.file_id, **kwargs)
        elif attachment.type == "audio":
            await manager.bot.send_audio(audio=attachment.file_id, **kwargs)
        elif attachment.type == "voice":
            await manager.bot.send_voice(voice=attachment.file_id, **kwargs)
        elif attachment.type == "video_note":
            kwargs.pop("caption", None)
            kwargs.pop("parse_mode", None)
            await manager.bot.send_video_note(video_note=attachment.file_id, **kwargs)
router = Router()
router.message.filter(
    F.message_thread_id.is_not(None),
    F.chat.type.in_(["group", "supergroup"]),
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
)


@router.message(Command("silent"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Toggles silent mode for a user in the group.
    If silent mode is disabled, it will be enabled, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.message_silent_mode:
        text = manager.text_message.get("silent_mode_disabled")
        with suppress(TelegramBadRequest):
            # Reply with the specified text
            await message.reply(text)

            # Unpin the chat message with the silent mode status
            await message.bot.unpin_chat_message(
                chat_id=message.chat.id,
                message_id=user_data.message_silent_id,
            )

        user_data.message_silent_mode = False
        user_data.message_silent_id = None
    else:
        text = manager.text_message.get("silent_mode_enabled")
        with suppress(TelegramBadRequest):
            # Reply with the specified text
            msg = await message.reply(text)

            # Pin the chat message with the silent mode status
            await msg.pin(disable_notification=True)

        user_data.message_silent_mode = True
        user_data.message_silent_id = msg.message_id

    await redis.update_user(user_data.id, user_data)


@router.message(Command("information"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Sends user information in response to the /information command.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    info = await fetch_user_info(manager.config.remnawave, user_data.id)
    if info:
        await message.reply(format_user_info(info, title="Remnawave: информация о пользователе"))
        return

    format_data = user_data.to_dict()
    safe_name = sanitize_display_name(format_data["full_name"], placeholder=f"User {user_data.id}")
    format_data["full_name"] = hbold(safe_name)
    text = manager.text_message.get("user_information")
    if not is_configured(manager.config.remnawave):
        text = "Remnawave не настроен. Резервная информация:\n\n" + text
    else:
        text = "Пользователь не найден в Remnawave. Резервная информация:\n\n" + text
    await message.reply(text.format_map(format_data))


@router.message(Command("del"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data:
        return

    if not message.reply_to_message:
        await message.reply("Используй /del ответом на сообщение оператора.")
        return

    target_message_id = message.reply_to_message.message_id
    linked_ids = await redis.get_message_links(target_message_id)
    if not linked_ids:
        await message.reply("Связанное сообщение у пользователя не найдено.")
        return

    for user_message_id in linked_ids:
        with suppress(TelegramBadRequest, TelegramAPIError):
            await manager.bot.delete_message(
                chat_id=user_data.id,
                message_id=user_message_id,
            )

    with suppress(TelegramBadRequest, TelegramAPIError):
        await manager.bot.delete_message(
            chat_id=message.chat.id,
            message_id=target_message_id,
        )

    await redis.delete_message_links(target_message_id)

    with suppress(TelegramBadRequest, TelegramAPIError):
        await message.delete()


async def _send_resolution_message(manager: Manager, settings: SettingsStorage, user_data: UserData) -> None:
    language_code = resolve_language_code(user_data.language_code)
    override = await settings.get_resolved_message(language_code)
    template = override or TextMessage(language_code).get("ticket_resolved_user")
    safe_name = sanitize_display_name(user_data.full_name, placeholder=f"User {user_data.id}")
    escaped_name = html.escape(safe_name)
    text = template.format(full_name=hbold(escaped_name))

    with suppress(TelegramBadRequest, TelegramAPIError):
        await manager.bot.send_message(
            chat_id=user_data.id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


async def _resolve_ticket(
    message: Message,
    manager: Manager,
    redis: RedisStorage,
    apscheduler: AsyncIOScheduler,
    settings: SettingsStorage,
    *,
    notify_user: bool,
) -> None:
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    user_data.ticket_status = "resolved"
    user_data.awaiting_reply = False
    user_data.operator_replied = False
    await redis.update_user(user_data.id, user_data)
    cancel_support_reminder(apscheduler, user_data.id)

    with suppress(TelegramBadRequest):
        await message.bot.edit_forum_topic(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            icon_custom_emoji_id=manager.config.bot.BOT_RESOLVED_EMOJI_ID,
        )

    if notify_user:
        await _send_resolution_message(manager, settings, user_data)

    await message.reply(manager.text_message.get("ticket_resolved"))


async def _reopen_ticket(
    message: Message,
    manager: Manager,
    redis: RedisStorage,
    apscheduler: AsyncIOScheduler,
    user_data: UserData,
) -> None:
    user_data.ticket_status = "open"
    user_data.awaiting_reply = False
    user_data.operator_replied = False
    await redis.update_user(user_data.id, user_data)
    cancel_support_reminder(apscheduler, user_data.id)

    with suppress(TelegramBadRequest):
        await message.bot.edit_forum_topic(
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
            icon_custom_emoji_id=manager.config.bot.BOT_EMOJI_ID,
        )

    await message.reply(manager.text_message.get("ticket_reopened"))


async def _update_panel_main_message(message: Message, manager: Manager, user_data: UserData) -> None:
    markup = main_keyboard(
        user_data.id,
        ticket_status=user_data.ticket_status,
    )
    try:
        await message.edit_text(
            panel_text(manager.text_message, user_data),
            reply_markup=markup,
        )
    except TelegramBadRequest as ex:
        if "message is not modified" in ex.message:
            with suppress(TelegramBadRequest):
                await message.edit_reply_markup(reply_markup=markup)
        else:
            raise

@router.message(Command("resolve"))
async def handler(message: Message, manager: Manager, redis: RedisStorage, apscheduler: AsyncIOScheduler, settings: SettingsStorage) -> None:
    await _resolve_ticket(
        message,
        manager,
        redis,
        apscheduler,
        settings,
        notify_user=True,
    )


@router.message(Command("resolvequiet"))
async def handler(message: Message, manager: Manager, redis: RedisStorage, apscheduler: AsyncIOScheduler, settings: SettingsStorage) -> None:
    await _resolve_ticket(
        message,
        manager,
        redis,
        apscheduler,
        settings,
        notify_user=False,
    )


@router.message(Command("menu"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data:
        return

    panel_message = await message.reply(
        panel_text(manager.text_message, user_data),
        reply_markup=main_keyboard(
            user_data.id,
            ticket_status=user_data.ticket_status,
        ),
    )
    user_data.panel_message_id = panel_message.message_id
    await redis.update_user(user_data.id, user_data)


@router.message(Command(commands=["ban"]))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Toggles the ban status for a user in the group.
    If the user is banned, they will be unbanned, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.is_banned:
        user_data.is_banned = False
        text = manager.text_message.get("user_unblocked")
    else:
        user_data.is_banned = True
        text = manager.text_message.get("user_blocked")

    # Reply with the specified text
    await message.reply(text)
    await redis.update_user(user_data.id, user_data)


router.callback_query.filter(
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
    F.message.chat.type.in_(["group", "supergroup"]),
    F.message.message_thread_id.is_not(None),
    F.data.startswith(PANEL_NAMESPACE),
)


@router.callback_query()
async def panel_callback(
    call: CallbackQuery,
    manager: Manager,
    redis: RedisStorage,
    apscheduler: AsyncIOScheduler,
    settings: SettingsStorage,
    quick_replies: QuickReplyStorage,
) -> None:
    parts = call.data.split(":")
    action = parts[1]

    if action == "status":
        sub_action = parts[2]
        user_id = int(parts[3])
        target = parts[4] if sub_action == "set" and len(parts) > 4 else None
    else:
        user_id = int(parts[2])
        sub_action = None
        target = None

    user_data = await redis.get_user(user_id)
    if not user_data:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    if action == "reply":
        safe_name = sanitize_display_name(user_data.full_name, placeholder=f"User {user_data.id}")
        prompt = manager.text_message.get("support_panel_reply_prompt").format(full_name=hbold(safe_name))
        placeholder = manager.text_message.get("support_panel_reply_placeholder")
        await call.message.answer(
            prompt,
            reply_markup=ForceReply(selective=True, input_field_placeholder=placeholder),
        )
        await call.answer(manager.text_message.get("support_panel_reply_hint"))

    elif action == "postpone":
        user_data.awaiting_reply = True
        await redis.update_user(user_data.id, user_data)
        schedule_support_reminder(
            apscheduler,
            bot_token=manager.config.bot.TOKEN,
            group_id=manager.config.bot.GROUP_ID,
            user_id=user_data.id,
            message_thread_id=user_data.message_thread_id,
            language_code=user_data.language_code,
            db_path=manager.config.sqlite.PATH,
        )
        await call.answer(manager.text_message.get("support_panel_postponed"))

    elif action == "status_menu":
        await call.message.edit_reply_markup(
            reply_markup=status_keyboard(
                user_id,
                ticket_status=user_data.ticket_status,
            )
        )
        await call.answer()

    elif action == "status" and sub_action == "back":
        await _update_panel_main_message(call.message, manager, user_data)
        await call.answer()

    elif action == "status" and sub_action == "set":
        if target in {"resolve", "resolvequiet"}:
            await _resolve_ticket(
                call.message,
                manager,
                redis,
                apscheduler,
                settings,
                notify_user=(target == "resolve"),
            )
            user_data = await redis.get_user(user_id)
        elif target == "open":
            await _reopen_ticket(
                call.message,
                manager,
                redis,
                apscheduler,
                user_data,
            )
            user_data = await redis.get_user(user_id)
        else:
            await call.answer()
            return

        if user_data:
            await _update_panel_main_message(call.message, manager, user_data)
            await call.answer(manager.text_message.get("support_panel_status_changed"))
        else:
            await call.answer("Пользователь не найден.", show_alert=True)
            return



    elif action == "quick":
        items = await quick_replies.list_items()
        if not items:
            await call.answer("Быстрые ответы не заданы.", show_alert=True)
            return

        builder = InlineKeyboardBuilder()
        for item in items:
            builder.button(text=item.title, callback_data=f"qr:send:{item.id}")
        builder.button(text="✖ Закрыть", callback_data="qr:close")
        builder.adjust(1)
        await call.message.answer(
            "Выберите быстрый ответ:",
            reply_markup=builder.as_markup(),
        )
        await call.answer()
        return
    elif action == "info":
        info = await fetch_user_info(manager.config.remnawave, user_data.id)
        if info:
            await call.message.answer(format_user_info(info, title="Remnawave: информация о пользователе"))
            await call.answer()
            return

        format_data = user_data.to_dict()
        safe_name = sanitize_display_name(format_data["full_name"], placeholder=f"User {user_data.id}")
        format_data["full_name"] = hbold(safe_name)
        text = manager.text_message.get("user_information")
        if not is_configured(manager.config.remnawave):
            text = "Remnawave не настроен. Резервная информация:\n\n" + text
        else:
            text = "Пользователь не найден в Remnawave. Резервная информация:\n\n" + text
        await call.message.answer(text.format_map(format_data))
        await call.answer()

    else:
        await call.answer()
        return

    # persist current panel message id
    latest = await redis.get_user(user_id)
    if latest:
        latest.panel_message_id = call.message.message_id
        await redis.update_user(user_id, latest)


@router.callback_query(F.data.startswith("qr:send:"))
async def quick_reply_send(
    call: CallbackQuery,
    manager: Manager,
    redis: RedisStorage,
    quick_replies: QuickReplyStorage,
) -> None:
    if call.message is None or call.message.message_thread_id is None:
        await call.answer()
        return

    user_data = await redis.get_by_message_thread_id(call.message.message_thread_id)
    if not user_data:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    item_id = call.data.split(":", maxsplit=2)[-1]
    item = await quick_replies.get_item(item_id)
    if item is None:
        await call.answer("Ответ не найден.", show_alert=True)
        return

    await _send_quick_reply(manager, item, chat_id=user_data.id)
    await _send_quick_reply(
        manager,
        item,
        chat_id=call.message.chat.id,
        message_thread_id=call.message.message_thread_id,
    )
    msg = await call.message.answer("✅ Быстрый ответ отправлен.")
    Manager.schedule_message_cleanup(msg)
    await call.answer()


@router.callback_query(F.data == "qr:close")
async def quick_reply_close(call: CallbackQuery) -> None:
    with suppress(TelegramBadRequest):
        await call.message.delete()
    await call.answer()
