from __future__ import annotations

from contextlib import suppress

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold

from app.bot.utils.redis.models import UserData
from app.bot.utils.security import sanitize_display_name
from app.bot.utils.texts import TextMessage

PANEL_NAMESPACE = "support_panel"


def panel_text(texts: TextMessage, user_data: UserData) -> str:
    status_key = "ticket_status_open" if user_data.ticket_status == "open" else "ticket_status_resolved"
    status_text = texts.get(status_key)
    safe_name = sanitize_display_name(user_data.full_name, placeholder=f"User {user_data.id}")
    return texts.get("support_panel_prompt").format(
        full_name=hbold(safe_name),
        status=status_text,
    )


def main_keyboard(user_id: int, *, ticket_status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💬 Ответить",
        callback_data=f"{PANEL_NAMESPACE}:reply:{user_id}",
    )
    builder.button(
        text="⏳ Отложить",
        callback_data=f"{PANEL_NAMESPACE}:postpone:{user_id}",
    )
    builder.button(
        text="🔁 Сменить статус",
        callback_data=f"{PANEL_NAMESPACE}:status_menu:{user_id}",
    )
    builder.button(
        text="ℹ️ Инфо",
        callback_data=f"{PANEL_NAMESPACE}:info:{user_id}",
    )
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def status_keyboard(user_id: int, *, ticket_status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ticket_status != "open":
        builder.button(
            text="🔄 Переоткрыть",
            callback_data=f"{PANEL_NAMESPACE}:status:set:{user_id}:open",
        )
    else:
        builder.button(
            text="✅ Решить",
            callback_data=f"{PANEL_NAMESPACE}:status:set:{user_id}:resolve",
        )
        builder.button(
            text="✅ Решить тихо",
            callback_data=f"{PANEL_NAMESPACE}:status:set:{user_id}:resolvequiet",
        )
    builder.button(
        text="⬅️ Назад",
        callback_data=f"{PANEL_NAMESPACE}:status:back:{user_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def remove_panel_message(bot, *, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    with suppress(Exception):
        bot.delete_message(chat_id, message_id)
