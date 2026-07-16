from __future__ import annotations

import html
from contextlib import suppress

from aiogram import F, Router
from aiogram.filters import Command, MagicData, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold

from app.bot.handlers.private.windows import Window
from app.bot.manager import Manager
from app.bot.utils.business_hours import format_hhmm, parse_hours_range
from app.bot.utils.redis import SettingsStorage
from app.bot.utils.texts import SUPPORTED_LANGUAGES, TextMessage


class BusinessHoursStates(StatesGroup):
    """FSM states for business-hours settings."""

    waiting_for_range = State()
    waiting_for_message = State()


router = Router(name="admin_business_hours")
router.message.filter(
    F.chat.type == "private",
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)
router.callback_query.filter(
    F.message.chat.type == "private",
    MagicData(F.event_from_user.id == F.config.bot.DEV_ID),  # type: ignore[attr-defined]
)


def _preview_text(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) > 80:
        normalized = f"{normalized[:77]}..."
    return html.escape(normalized)


def _default_message(language: str) -> str:
    return TextMessage(language).get("outside_business_hours")


async def _send_menu(manager: Manager, settings: SettingsStorage) -> None:
    hours = await settings.get_business_hours()
    overrides = await settings.get_all_business_hours_messages()

    status = "включено" if hours.enabled else "выключено"
    lines = [
        "<b>Рабочее время поддержки</b>",
        f"Статус: <b>{status}</b>",
        f"Часы: <b>{format_hhmm(hours.start)}-{format_hhmm(hours.end)}</b> по Москве",
        "",
        "Вне этих часов бот отправит пользователю настраиваемое уведомление.",
        "",
        "<b>Тексты:</b>",
    ]

    for language, title in SUPPORTED_LANGUAGES.items():
        message = overrides.get(language, _default_message(language))
        source = "кастом" if language in overrides else "по умолчанию"
        lines.append(f"{hbold(title)} — {_preview_text(message)} ({source})")

    builder = InlineKeyboardBuilder()
    toggle_text = "Выключить" if hours.enabled else "Включить"
    builder.button(text=f"⏱ {toggle_text}", callback_data="hours:toggle")
    builder.button(text="🕘 Изменить часы", callback_data="hours:set_range")
    for language, title in SUPPORTED_LANGUAGES.items():
        suffix = " (обновлено)" if language in overrides else ""
        builder.button(text=f"✏️ {title}{suffix}", callback_data=f"hours:set_message:{language}")
    builder.button(text="⬅️ Назад", callback_data="admin:menu")
    builder.button(text="✖️ Закрыть", callback_data="hours:close")
    builder.adjust(1)

    await manager.state.set_state(None)
    await manager.state.update_data(hours_language=None)
    await manager.send_message("\n".join(lines), reply_markup=builder.as_markup(), replace_previous=False)


@router.message(Command("hours"))
async def show_menu(message: Message, manager: Manager, settings: SettingsStorage) -> None:
    await _send_menu(manager, settings)
    await manager.delete_message(message)


@router.callback_query(F.data == "admin:business_hours")
async def open_from_menu(call: CallbackQuery, manager: Manager, settings: SettingsStorage) -> None:
    await _send_menu(manager, settings)
    await call.answer()


@router.callback_query(F.data == "hours:toggle")
async def toggle_hours(call: CallbackQuery, manager: Manager, settings: SettingsStorage) -> None:
    hours = await settings.get_business_hours()
    await settings.set_business_hours_enabled(not hours.enabled)
    await _send_menu(manager, settings)
    await call.answer("Сохранено")


@router.callback_query(F.data == "hours:set_range")
async def start_range_edit(call: CallbackQuery, manager: Manager, settings: SettingsStorage) -> None:
    hours = await settings.get_business_hours()
    await manager.state.set_state(BusinessHoursStates.waiting_for_range)
    await manager.send_message(
        "Отправьте рабочее время в формате <code>09:00-00:00</code>.\n"
        f"Текущее значение: <b>{format_hhmm(hours.start)}-{format_hhmm(hours.end)}</b> по Москве.",
        replace_previous=False,
    )
    await call.answer()


@router.message(StateFilter(BusinessHoursStates.waiting_for_range))
async def save_range(message: Message, manager: Manager, settings: SettingsStorage) -> None:
    content = (message.text or message.caption or "").strip()
    try:
        start, end = parse_hours_range(content)
    except (TypeError, ValueError):
        await message.answer("Не понял время. Используйте формат <code>09:00-00:00</code>.")
        return

    await settings.set_business_hours_range(start, end)
    await manager.state.set_state(None)
    await manager.delete_message(message)
    await _send_menu(manager, settings)


@router.callback_query(F.data.startswith("hours:set_message:"))
async def start_message_edit(call: CallbackQuery, manager: Manager, settings: SettingsStorage) -> None:
    language = call.data.split(":", maxsplit=2)[-1]
    if language not in SUPPORTED_LANGUAGES:
        await call.answer("Неизвестный язык.", show_alert=True)
        return

    current = await settings.get_business_hours_message(language) or _default_message(language)
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Сбросить", callback_data=f"hours:reset_message:{language}")
    builder.button(text="⬅️ Назад", callback_data="hours:back")
    builder.adjust(1)

    await manager.state.set_state(BusinessHoursStates.waiting_for_message)
    await manager.state.update_data(hours_language=language)
    await manager.send_message(
        f"{hbold(SUPPORTED_LANGUAGES[language])}\n\n"
        "Отправьте новый текст уведомления одним сообщением.\n\n"
        "<b>Текущее значение:</b>\n"
        f"<code>{html.escape(current)}</code>",
        reply_markup=builder.as_markup(),
        replace_previous=False,
    )
    await call.answer()


@router.message(StateFilter(BusinessHoursStates.waiting_for_message))
async def save_message(message: Message, manager: Manager, settings: SettingsStorage) -> None:
    state_data = await manager.state.get_data()
    language = state_data.get("hours_language")
    content = (message.text or message.caption or "").strip()

    if language not in SUPPORTED_LANGUAGES:
        await manager.state.set_state(None)
        await _send_menu(manager, settings)
        await message.answer("Не удалось определить язык. Попробуйте еще раз.")
        return

    if not content:
        await message.answer("Пожалуйста, отправьте непустой текст.")
        return

    await settings.set_business_hours_message(language, content)
    await manager.state.update_data(hours_language=None)
    await manager.delete_message(message)
    await _send_menu(manager, settings)


@router.callback_query(F.data.startswith("hours:reset_message:"))
async def reset_message(call: CallbackQuery, manager: Manager, settings: SettingsStorage) -> None:
    language = call.data.split(":", maxsplit=2)[-1]
    if language not in SUPPORTED_LANGUAGES:
        await call.answer("Неизвестный язык.", show_alert=True)
        return

    await settings.reset_business_hours_message(language)
    await _send_menu(manager, settings)
    await call.answer("Сброшено")


@router.callback_query(F.data == "hours:back")
async def back_to_menu(call: CallbackQuery, manager: Manager, settings: SettingsStorage) -> None:
    await _send_menu(manager, settings)
    await call.answer()


@router.callback_query(F.data == "hours:close")
async def close_menu(call: CallbackQuery, manager: Manager) -> None:
    await manager.state.set_state(None)
    await manager.state.update_data(hours_language=None)
    with suppress(Exception):
        await call.message.delete()
    await Window.main_menu(manager)
    await call.answer("Меню закрыто")
