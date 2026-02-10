from __future__ import annotations

import logging
import html
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram.utils.markdown import hbold, hcode
from remnawave import RemnawaveSDK

from app.config import RemnawaveConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RemnawaveInfo:
    username: str
    telegram_id: int | None
    status: str
    user_id: int | None
    created_at: datetime
    expire_at: datetime
    used_traffic_bytes: float
    lifetime_traffic_bytes: float
    last_connected_node_name: str | None
    last_connected_at: datetime | None
    subscription_url: str | None
    internal_squads: list[str]
    external_squad: str | None
    users_found: int = 1
    devices_count: int | None = None
    devices_limit: int | None = None
    devices_count: int | None = None
    devices_limit: int | None = None


def _bytes_to_gb(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{value / (1024 ** 3):.2f} GB"
    except Exception:
        return "—"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    msk = timezone(timedelta(hours=3))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(msk).strftime("%Y-%m-%d %H:%M:%S")




def _format_devices(info: RemnawaveInfo) -> str:
    count = info.devices_count
    limit = info.devices_limit
    if count is None and limit is None:
        return "?"
    if count is not None and limit is not None:
        return f"{count}/{limit}"
    if limit is not None:
        return str(limit)
    return str(count)




def _format_devices(info: RemnawaveInfo) -> str:
    count = info.devices_count
    limit = info.devices_limit
    if count is None and limit is None:
        return "?"
    if count is not None and limit is not None:
        return f"{count}/{limit}"
    if limit is not None:
        return str(limit)
    return str(count)


def is_configured(config: RemnawaveConfig) -> bool:
    return bool(config.API_BASE and config.API_TOKEN)


async def fetch_user_info(config: RemnawaveConfig, telegram_id: int) -> RemnawaveInfo | None:
    if not is_configured(config):
        return None

    sdk = RemnawaveSDK(
        base_url=config.API_BASE,
        token=config.API_TOKEN,
        caddy_token=config.CADDY_TOKEN,
        ssl_ignore=config.SSL_IGNORE,
    )
    try:
        users = await sdk.users.get_users_by_telegram_id(str(telegram_id))
        if not users:
            return None

        user = users[0]
        users_found = len(users)

        user_id = getattr(user, 'id', None)
        if user_id is None:
            user_id = getattr(user, 'user_id', None)

        last_node_name: Optional[str] = None
        last_connected_at = user.user_traffic.online_at
        if user.user_traffic.last_connected_node_uuid:
            try:
                node = await sdk.nodes.get_one_node(str(user.user_traffic.last_connected_node_uuid))
                last_node_name = node.name
            except Exception as exc:
                logger.warning("Failed to load node %s: %s", user.user_traffic.last_connected_node_uuid, exc)

        external_squad_name: Optional[str] = None
        if user.external_squad_uuid:
            try:
                squad = await sdk.external_squads.get_external_squad_by_uuid(str(user.external_squad_uuid))
                external_squad_name = getattr(squad, "name", None)
            except Exception as exc:
                logger.warning("Failed to load external squad %s: %s", user.external_squad_uuid, exc)

        internal_squads = []
        if user.active_internal_squads:
            for squad in user.active_internal_squads:
                name = getattr(squad, "name", None)
                if name:
                    internal_squads.append(name)


        devices_count: Optional[int] = None
        devices_limit: Optional[int] = getattr(user, 'hwid_device_limit', None)
        if getattr(user, 'uuid', None):
            try:
                devices = await sdk.hwid.get_hwid_user(str(user.uuid))
                devices_count = getattr(devices, 'total', None)
            except Exception as exc:
                logger.warning("Failed to load HWID devices for %s: %s", user.uuid, exc)


        devices_count: Optional[int] = None
        devices_limit: Optional[int] = getattr(user, 'hwid_device_limit', None)
        if getattr(user, 'uuid', None):
            try:
                devices = await sdk.hwid.get_hwid_user(str(user.uuid))
                devices_count = getattr(devices, 'total', None)
            except Exception as exc:
                logger.warning("Failed to load HWID devices for %s: %s", user.uuid, exc)

        return RemnawaveInfo(
            username=user.username,
            telegram_id=user.telegram_id,
            status=str(user.status),
            user_id=user_id,
            created_at=user.created_at,
            expire_at=user.expire_at,
            used_traffic_bytes=user.user_traffic.used_traffic_bytes,
            lifetime_traffic_bytes=user.user_traffic.lifetime_used_traffic_bytes,
            last_connected_node_name=last_node_name,
            last_connected_at=last_connected_at,
            subscription_url=getattr(user, "subscription_url", None),
            internal_squads=internal_squads,
            external_squad=external_squad_name,
            users_found=users_found,
            devices_count=devices_count,
            devices_limit=devices_limit,
        )
    except Exception as exc:
        logger.exception("Remnawave lookup failed for telegram_id=%s: %s", telegram_id, exc)
        return None
    finally:
        await sdk._client.aclose()


def format_user_info(info: RemnawaveInfo, *, title: str) -> str:
    internal_squads = [name.strip() for name in info.internal_squads if name and name.strip()]
    internal_lower = {name.lower() for name in internal_squads}
    if any(name == "trial" for name in internal_lower):
        subscription_kind = "НИЩЕБРОД"
    elif "germany" in internal_lower and "white" in internal_lower:
        subscription_kind = "ПЛАТНАЯ + БС"
    elif "germany" in internal_lower:
        subscription_kind = "ПЛАТНАЯ"
    elif internal_squads:
        subscription_kind = ", ".join(html.escape(name) for name in internal_squads)
    else:
        subscription_kind = "—"
    node = info.last_connected_node_name or "—"

    lines = [
        hbold(title),
        "",
        f"👤 Логин: {hcode(info.username)}",
        f"🔢 ID пользователя: {hcode(info.user_id) if info.user_id else '—'}",
        f"🆔 Telegram ID: {hcode(info.telegram_id) if info.telegram_id else '—'}",
        f"✅ Статус: {hcode(info.status)}",
        f"🗓 Первое подключение: {_format_datetime(info.created_at)}",
        f"🗓 Подписка активна до: {_format_datetime(info.expire_at)}",
        f"📶 Трафик за месяц: {_bytes_to_gb(info.used_traffic_bytes)}",
        f"📶 Трафик за всё время: {_bytes_to_gb(info.lifetime_traffic_bytes)}",
        f"📱 Устройства: {_format_devices(info)}",
        f"📱 Устройства: {_format_devices(info)}",
        f"🔗 Подписная ссылка: {hcode(info.subscription_url) if info.subscription_url else '—'}",
        f"🛰 Нода: {hcode(node)}",
        f"🕒 Последний онлайн: {_format_datetime(info.last_connected_at)}",
        f"🧩 Вид подписки: {subscription_kind}",
    ]

    if info.users_found > 1:
        lines.append(f"👥 Найдено пользователей по Telegram ID: {info.users_found}")

    return "\n".join(lines)
