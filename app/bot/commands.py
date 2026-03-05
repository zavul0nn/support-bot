from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from app.bot.utils.texts import SUPPORTED_LANGUAGES
from app.config import Config


async def setup(bot: Bot, config: Config) -> None:
    """
    Set up bot commands for various scopes and languages.

    :param bot: The Bot object.
    :param config: The Config object.
    """
    commands = {
        "en": [
            BotCommand(command="start", description="Restart the bot"),
        ],
        "ru": [
            BotCommand(command="start", description="Перезапустить бота"),
        ],
    }

    if len(SUPPORTED_LANGUAGES) > 1:
        commands["en"].append(
            BotCommand(command="language", description="Change language"),
        )
        commands["ru"].append(
            BotCommand(command="language", description="Выбрать язык"),
        )

    group_commands = {
        "en": [
            BotCommand(command="ban", description="Block or unblock a user"),
            BotCommand(command="silent", description="Toggle silent mode"),
            BotCommand(command="information", description="Show user information"),
            BotCommand(command="menu", description="Open ticket action menu"),
            BotCommand(command="resolve", description="Mark ticket as resolved"),
            BotCommand(command="resolvequiet", description="Resolve ticket without user message"),
        ],
        "ru": [
            BotCommand(command="ban", description="Заблокировать/разблокировать пользователя"),
            BotCommand(command="silent", description="Включить/выключить тихий режим"),
            BotCommand(command="information", description="Показать информацию о пользователе"),
            BotCommand(command="menu", description="Открыть меню действий тикета"),
            BotCommand(command="resolve", description="Отметить тикет решённым"),
            BotCommand(command="resolvequiet", description="Закрыть тикет без сообщения пользователю"),
        ],
    }

    admin_commands = {
        "en": commands["en"].copy() + [
            BotCommand(command="banned", description="Show banned users"),
            BotCommand(command="unban", description="Unban a user"),
            BotCommand(command="newsletter", description="Open the newsletter menu"),
            BotCommand(command="greeting", description="Open the greeting settings"),
            BotCommand(command="closing", description="Configure closing message"),
        ],
        "ru": commands["ru"].copy() + [
            BotCommand(command="banned", description="Показать забаненных пользователей"),
            BotCommand(command="unban", description="Разбанить пользователя"),
            BotCommand(command="newsletter", description="Меню рассылки"),
            BotCommand(command="greeting", description="Настройки приветствия"),
            BotCommand(command="closing", description="Настроить сообщение после закрытия"),
        ],
    }

    try:
        await bot.set_my_commands(
            commands=admin_commands["en"],
            scope=BotCommandScopeChat(chat_id=config.bot.DEV_ID),
        )
        await bot.set_my_commands(
            commands=admin_commands["ru"],
            scope=BotCommandScopeChat(chat_id=config.bot.DEV_ID),
            language_code="ru",
        )
    except TelegramBadRequest as exc:
        raise ValueError(f"Chat with DEV_ID {config.bot.DEV_ID} not found.") from exc

    await bot.set_my_commands(
        commands=commands["en"],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        commands=commands["ru"],
        scope=BotCommandScopeAllPrivateChats(),
        language_code="ru",
    )
    await bot.set_my_commands(
        commands=group_commands["en"],
        scope=BotCommandScopeAllGroupChats(),
    )
    await bot.set_my_commands(
        commands=group_commands["ru"],
        scope=BotCommandScopeAllGroupChats(),
        language_code="ru",
    )


async def delete(bot: Bot, config: Config) -> None:
    """
    Delete bot commands for various scopes and languages.

    :param bot: The Bot object.
    :param config: The Config object.
    """
    try:
        await bot.delete_my_commands(
            scope=BotCommandScopeChat(chat_id=config.bot.DEV_ID),
        )
        await bot.delete_my_commands(
            scope=BotCommandScopeChat(chat_id=config.bot.DEV_ID),
            language_code="ru",
        )
    except TelegramBadRequest as exc:
        raise ValueError(f"Chat with DEV_ID {config.bot.DEV_ID} not found.") from exc

    await bot.delete_my_commands(
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.delete_my_commands(
        scope=BotCommandScopeAllPrivateChats(),
        language_code="ru",
    )
    await bot.delete_my_commands(
        scope=BotCommandScopeAllGroupChats(),
    )
    await bot.delete_my_commands(
        scope=BotCommandScopeAllGroupChats(),
        language_code="ru",
    )
