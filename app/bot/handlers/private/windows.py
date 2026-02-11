from contextlib import suppress

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold

from app.bot.manager import Manager
from app.bot.utils.create_forum_topic import get_or_create_forum_topic
from app.bot.utils.redis import SettingsStorage, RedisStorage
from app.bot.utils.redis.models import UserData

from aiogram.types import InlineKeyboardMarkup as Markup
from aiogram.types import InlineKeyboardButton as Button

from app.bot.utils.texts import SUPPORTED_LANGUAGES


def select_language_markup() -> Markup:
    """
    Generate an inline keyboard markup for selecting the language.

    :return: InlineKeyboardMarkup
    """

    builder = InlineKeyboardBuilder().row(
        *[
            Button(text=text, callback_data=callback_data)
            for callback_data, text in SUPPORTED_LANGUAGES.items()
        ], width=2
    )
    return builder.as_markup()


def admin_main_menu_markup(manager: Manager) -> InlineKeyboardBuilder | None:
    """
    Generate admin controls for the main menu when DEV_ID opens the bot.

    :param manager: Manager object.
    :return: InlineKeyboardBuilder or None.
    """
    user = getattr(manager, "user", None)
    config = getattr(manager, "config", None)
    user_id = getattr(user, "id", None)
    dev_id = getattr(getattr(config, "bot", None), "DEV_ID", None)
    if user_id is None or dev_id is None or user_id != dev_id:
        return None

    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 Рассылка", callback_data="admin:newsletter")
    builder.button(text="👋 Приветствия", callback_data="admin:greeting")
    builder.button(text="✅ Сообщения закрытия", callback_data="admin:closing")
    builder.button(text="🚫 Забаненные", callback_data="admin:banned")
    builder.button(text="📚 FAQ", callback_data="admin:faq")
    builder.button(text="⚡ Быстрые ответы", callback_data="admin:quick_replies")
    builder.adjust(2)
    return builder


class Window:

    @staticmethod
    async def select_language(manager: Manager) -> None:
        """
        Display the window for selecting the language.

        :param manager: Manager object.
        :return: None
        """
        text = manager.text_message.get("select_language")
        with suppress(IndexError, KeyError):
            text = text.format(full_name=hbold(manager.user.full_name))
        reply_markup = select_language_markup()
        await manager.send_message(text, reply_markup=reply_markup)

    @staticmethod
    async def main_menu(manager: Manager, **_) -> None:
        """
        Display the main menu window.

        :param manager: Manager object.
        :return: None
        """
        language_code = manager.text_message.language_code
        custom_text = None

        settings: SettingsStorage | None = manager.middleware_data.get("settings")
        if settings is not None:
            custom_text = await settings.get_greeting(language_code)

        text = custom_text or manager.text_message.get("main_menu")
        with suppress(IndexError, KeyError):
            text = text.format(full_name=hbold(manager.user.full_name))

        builder = InlineKeyboardBuilder()
        has_buttons = False

        faq_storage = manager.middleware_data.get("faq")
        if faq_storage and await faq_storage.has_items():
            builder.button(text="📚 Часто задаваемые вопросы", callback_data="faq:open")
            builder.adjust(1)
            has_buttons = True

        admin_builder = admin_main_menu_markup(manager)
        if admin_builder:
            builder.attach(admin_builder)
            has_buttons = True

        reply_markup = builder.as_markup() if has_buttons else None

        await manager.send_message(text, reply_markup=reply_markup, replace_previous=False)
        await manager.state.set_state(None)

        redis: RedisStorage | None = manager.middleware_data.get("redis")
        user_data: UserData | None = manager.middleware_data.get("user_data")
        if redis is not None and user_data is not None:
            await get_or_create_forum_topic(manager.bot, redis, manager.config, user_data)

    @staticmethod
    async def change_language(manager: Manager) -> None:
        """
        Display the window for changing the language.

        :param manager: Manager object.
        :return: None
        """
        text = manager.text_message.get("change_language")
        reply_markup = select_language_markup()
        await manager.send_message(text, reply_markup=reply_markup)

