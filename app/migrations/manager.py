from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

from aiogram import Bot

from app.bot.utils.redis import RedisStorage
from app.bot.utils.sqlite import SQLiteDatabase
from app.config import Config

from .panel import ensure_operator_replied_flag
from .security import sanitize_existing_display_names

logger = logging.getLogger(__name__)

MigrationCallback = Callable[["MigrationContext"], Awaitable[None]]


@dataclass(slots=True)
class Migration:
    version: int
    description: str
    callback: MigrationCallback


@dataclass(slots=True)
class MigrationContext:
    config: Config
    bot: Bot
    db: SQLiteDatabase
    storage: RedisStorage
    throttle_delay: float = 0.05

    async def sleep(self) -> None:
        if self.throttle_delay > 0:
            await asyncio.sleep(self.throttle_delay)


class MigrationManager:
    VERSION_KEY = "support_bot:migration_version"

    def __init__(self, *, config: Config, bot: Bot, db: SQLiteDatabase) -> None:
        self.config = config
        self.bot = bot
        self.db = db
        self.storage = RedisStorage(db)

    async def _get_current_version(self) -> int:
        value = await self.db.get_meta(self.VERSION_KEY)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _set_current_version(self, version: int) -> None:
        await self.db.set_meta(self.VERSION_KEY, str(version))

    async def run_pending(self) -> None:
        current_version = await self._get_current_version()
        pending = [
            migration for migration in self._get_migrations() if migration.version > current_version
        ]
        if not pending:
            logger.info("No migrations required (current version=%s).", current_version)
            return

        context = MigrationContext(
            config=self.config,
            bot=self.bot,
            db=self.db,
            storage=self.storage,
        )

        for migration in sorted(pending, key=lambda m: m.version):
            logger.info("Starting migration %s: %s", migration.version, migration.description)
            await migration.callback(context)
            await self._set_current_version(migration.version)
            logger.info("Migration %s completed.", migration.version)

    @staticmethod
    def _get_migrations() -> Iterable[Migration]:
        return MIGRATIONS


async def run_migrations(*, config: Config, bot: Bot, db: SQLiteDatabase) -> None:
    manager = MigrationManager(config=config, bot=bot, db=db)
    await manager.run_pending()


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        description="Санитация отображаемых имен и переименование существующих тем.",
        callback=sanitize_existing_display_names,
    ),
    Migration(
        version=2,
        description="Initialize operator_replied flag for existing users.",
        callback=ensure_operator_replied_flag,
    ),
)
