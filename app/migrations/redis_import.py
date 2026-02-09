from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.bot.utils.redis.models import UserData
from app.bot.utils.sqlite import SQLiteDatabase
from app.config import Config

logger = logging.getLogger(__name__)


USERS_KEY = "users"
SETTINGS_KEY = "settings"
FAQ_ITEMS_KEY = "faq:items"
FAQ_ORDER_KEY = "faq:order"
MIGRATION_VERSION_KEY = "support_bot:migration_version"
REDIS_MIGRATED_KEY = "redis_migrated"
REDIS_MIGRATED_AT_KEY = "redis_migrated_at"


async def migrate_from_redis_if_needed(*, config: Config, db: SQLiteDatabase) -> None:
    if config.redis is None or not config.redis_migrate_on_start:
        return

    migrated_flag = await db.get_meta(REDIS_MIGRATED_KEY)
    if migrated_flag == "1":
        return

    if await db.has_any_data():
        await db.set_meta(REDIS_MIGRATED_KEY, "skipped_existing")
        logger.info("SQLite already has data; skipping Redis migration.")
        return

    redis = Redis.from_url(config.redis.dsn())
    try:
        await redis.ping()
    except Exception as exc:
        await redis.close()
        logger.warning("Redis migration skipped: %s", exc)
        return

    try:
        users_raw = await redis.hgetall(USERS_KEY)
        settings_raw = await redis.hgetall(SETTINGS_KEY)
        faq_order_raw = await redis.lrange(FAQ_ORDER_KEY, 0, -1)
        faq_items_raw = await redis.hgetall(FAQ_ITEMS_KEY)
        migration_version = await redis.get(MIGRATION_VERSION_KEY)

        logger.info(
            "Redis migration starting: users=%s settings=%s faq_items=%s faq_order=%s",
            len(users_raw),
            len(settings_raw),
            len(faq_items_raw),
            len(faq_order_raw),
        )

        users = []
        for key, value in users_raw.items():
            user_id = int(key.decode() if isinstance(key, bytes) else key)
            payload = json.loads(value.decode() if isinstance(value, bytes) else value)
            payload.setdefault("id", user_id)
            user = UserData(**payload)
            users.append(
                (
                    user.id,
                    user.message_thread_id,
                    user.message_silent_id,
                    int(bool(user.message_silent_mode)),
                    user.full_name,
                    user.username,
                    user.state,
                    int(bool(user.is_banned)),
                    user.language_code,
                    user.ticket_status,
                    int(bool(user.awaiting_reply)),
                    user.last_user_message_at,
                    user.created_at,
                    user.panel_message_id,
                    int(bool(user.operator_replied)),
                )
            )

        await db.executemany(
            """
            INSERT INTO users (
                id,
                message_thread_id,
                message_silent_id,
                message_silent_mode,
                full_name,
                username,
                state,
                is_banned,
                language_code,
                ticket_status,
                awaiting_reply,
                last_user_message_at,
                created_at,
                panel_message_id,
                operator_replied
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                message_thread_id = excluded.message_thread_id,
                message_silent_id = excluded.message_silent_id,
                message_silent_mode = excluded.message_silent_mode,
                full_name = excluded.full_name,
                username = excluded.username,
                state = excluded.state,
                is_banned = excluded.is_banned,
                language_code = excluded.language_code,
                ticket_status = excluded.ticket_status,
                awaiting_reply = excluded.awaiting_reply,
                last_user_message_at = excluded.last_user_message_at,
                created_at = excluded.created_at,
                panel_message_id = excluded.panel_message_id,
                operator_replied = excluded.operator_replied
            """,
            users,
        )

        settings_rows = []
        for key, value in settings_raw.items():
            decoded_key = key.decode() if isinstance(key, bytes) else key
            decoded_value = value.decode() if isinstance(value, bytes) else value
            settings_rows.append((decoded_key, decoded_value))

        await db.executemany(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            settings_rows,
        )

        faq_order = [
            (item_id.decode() if isinstance(item_id, bytes) else item_id)
            for item_id in faq_order_raw
        ]
        faq_rows = []
        if faq_order:
            for index, item_id in enumerate(faq_order, start=1):
                payload = faq_items_raw.get(item_id.encode()) or faq_items_raw.get(item_id)
                if payload is None:
                    continue
                payload = payload.decode() if isinstance(payload, bytes) else payload
                faq_rows.append((item_id, payload, index))
        else:
            for index, (item_id, payload) in enumerate(faq_items_raw.items(), start=1):
                decoded_id = item_id.decode() if isinstance(item_id, bytes) else item_id
                decoded_payload = payload.decode() if isinstance(payload, bytes) else payload
                faq_rows.append((decoded_id, decoded_payload, index))

        await db.executemany(
            "INSERT INTO faq_items (id, payload, sort_order) VALUES (?, ?, ?)",
            faq_rows,
        )

        if migration_version is not None:
            version_value = migration_version.decode() if isinstance(migration_version, bytes) else migration_version
            await db.set_meta(MIGRATION_VERSION_KEY, str(version_value))
            logger.info("Migrated migration_version=%s from Redis.", version_value)

        await db.set_meta(REDIS_MIGRATED_KEY, "1")
        await db.set_meta(REDIS_MIGRATED_AT_KEY, datetime.now(timezone.utc).isoformat())
        logger.info(
            "Redis migration completed: users=%s, settings=%s, faq=%s",
            len(users),
            len(settings_rows),
            len(faq_rows),
        )
        logger.warning(
            "Redis migration finished. You can remove Redis from docker-compose and unset REDIS_HOST."
        )
    finally:
        await redis.close()
