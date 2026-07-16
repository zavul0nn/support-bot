import asyncio
import logging
import time
from pathlib import Path

from aiogram import Bot, Dispatcher
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .bot import commands
from .bot.handlers import include_routers
from .bot.middlewares import register_middlewares
from .bot.utils.bot_factory import create_bot
from .bot.utils.business_hours import MOSCOW_TZ
from .bot.utils.fsm_storage import SQLiteFSMStorage
from .bot.utils.sqlite import SQLiteDatabase
from .config import load_config, Config
from .logger import setup_logger
from .migrations import run_migrations
from .migrations.redis_import import migrate_from_redis_if_needed


async def on_shutdown(
    apscheduler: AsyncIOScheduler,
    dispatcher: Dispatcher,
    config: Config,
    bot: Bot,
    db: SQLiteDatabase,
) -> None:
    """
    Shutdown event handler. This runs when the bot shuts down.

    :param apscheduler: AsyncIOScheduler: The apscheduler instance.
    :param dispatcher: Dispatcher: The bot dispatcher.
    :param config: Config: The config instance.
    :param bot: Bot: The bot instance.
    """
    # Stop apscheduler
    apscheduler.shutdown()
    # Delete commands and close storage when shutting down
    await commands.delete(bot, config)
    await dispatcher.storage.close()
    await db.close()
    await bot.delete_webhook()
    await bot.session.close()


async def on_startup(
    apscheduler: AsyncIOScheduler,
    config: Config,
    bot: Bot,
) -> None:
    """
    Startup event handler. This runs when the bot starts up.

    :param apscheduler: AsyncIOScheduler: The apscheduler instance.
    :param config: Config: The config instance.
    :param bot: Bot: The bot instance.
    """
    # Start apscheduler
    apscheduler.start()
    # Setup commands when starting up
    await commands.setup(bot, config)


async def main() -> None:
    """
    Main function that initializes the bot and starts the event loop.
    """
    logger = logging.getLogger("support_bot.startup")

    # Load config
    config = load_config()

    logger.info("🚀 Запуск support-bot…")
    logger.info("SQLite: %s", config.sqlite.PATH)
    logger.info("👤 DEV_ID: %s", config.bot.DEV_ID)
    logger.info("🗣️  Язык по умолчанию: %s", config.bot.DEFAULT_LANGUAGE)
    logger.info(
        "🧭 Подсказка выбора языка: %s",
        "включена" if config.bot.LANGUAGE_PROMPT_ENABLED else "выключена",
    )
    logger.info(
        "⏰ Напоминания операторам: %s",
        "активны" if config.bot.REMINDERS_ENABLED else "отключены",
    )

    # Initialize SQLite database
    base_dir = Path(__file__).resolve().parent.parent
    db_path = Path(config.sqlite.PATH)
    if not db_path.is_absolute():
        db_path = (base_dir / db_path).resolve()
    db = SQLiteDatabase(path=db_path)
    await db.connect()

    # Initialize apscheduler
    job_store = SQLAlchemyJobStore(url=f"sqlite:///{db_path.as_posix()}")
    apscheduler = AsyncIOScheduler(
        jobstores={"default": job_store},
        timezone=MOSCOW_TZ,
    )

    # Initialize FSM storage
    storage = SQLiteFSMStorage(db)

    # Create Bot and Dispatcher instances
    bot = create_bot(token=config.bot.TOKEN, proxy_url=config.bot.PROXY_URL)
    dp = Dispatcher(
        apscheduler=apscheduler,
        storage=storage,
        config=config,
        bot=bot,
        db=db,
    )

    # Register startup handler
    dp.startup.register(on_startup)
    # Register shutdown handler
    dp.shutdown.register(on_shutdown)

    # Include routes
    logger.info("🧭 Подключаем роутеры…")
    include_routers(dp)
    logger.info("✅ Роутеры подключены")
    # Register middlewares
    logger.info("🧱 Регистрируем middleware…")
    register_middlewares(
        dp, config=config, db=db, apscheduler=apscheduler
    )
    logger.info("✅ Middleware зарегистрированы")

    # Migrate existing data from Redis if needed
    await migrate_from_redis_if_needed(config=config, db=db)

    # Apply pending migrations before starting polling
    logger.info("🧹 Запускаем миграции…")
    migration_started = time.perf_counter()
    await run_migrations(config=config, bot=bot, db=db)
    logger.info(
        "✅ Миграции завершены за %.2f с",
        time.perf_counter() - migration_started,
    )

    # Start the bot
    await bot.delete_webhook()
    logger.info("🤖 Бот готов к приёму обновлений")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    # Set up logging
    setup_logger()
    # Run the bot
    asyncio.run(main())
