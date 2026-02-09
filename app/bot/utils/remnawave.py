from __future__ import annotations

import logging
import html
from dataclasses import dataclass
from datetime import datetime
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
    created_at: datetime
    expire_at: datetime
    used_traffic_bytes: float
    lifetime_traffic_bytes: float
    last_connected_node_name: str | None
    last_connected_at: datetime | None
    internal_squads: list[str]
    external_squad: str | None
    users_found: int = 1


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
    return value.strftime("%Y-%m-%d %H:%M:%S")


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

        return RemnawaveInfo(
            username=user.username,
            telegram_id=user.telegram_id,
            status=str(user.status),
            created_at=user.created_at,
            expire_at=user.expire_at,
            used_traffic_bytes=user.user_traffic.used_traffic_bytes,
            lifetime_traffic_bytes=user.user_traffic.lifetime_used_traffic_bytes,
            last_connected_node_name=last_node_name,
            last_connected_at=last_connected_at,
            internal_squads=internal_squads,
            external_squad=external_squad_name,
            users_found=users_found,
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
    elif any(name in {"germany", "white"} for name in internal_lower):
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
        f"🆔 Telegram ID: {hcode(info.telegram_id) if info.telegram_id else '—'}",
        f"✅ Статус: {hcode(info.status)}",
        f"🗓 Первое подключение: {_format_datetime(info.created_at)}",
        f"🗓 Подписка активна до: {_format_datetime(info.expire_at)}",
        f"📶 Трафик за месяц: {_bytes_to_gb(info.used_traffic_bytes)}",
        f"📶 Трафик за всё время: {_bytes_to_gb(info.lifetime_traffic_bytes)}",
        f"🛰 Нода: {hcode(node)}",
        f"🕒 Последний онлайн: {_format_datetime(info.last_connected_at)}",
        f"🧩 Вид подписки: {subscription_kind}",
    ]

    if info.users_found > 1:
        lines.append(f"👥 Найдено пользователей по Telegram ID: {info.users_found}")

    return "\n".join(lines)
