from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram.utils.markdown import hbold, hcode
from remnawave import RemnawaveSDK

from app.config import RemnawaveConfig

logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))
DAILY_TRAFFIC_NODES_LIMIT = 1000


@dataclass(slots=True)
class TrafficNodeUsage:
    name: str
    total_bytes: int
    country_code: str | None = None


@dataclass(slots=True)
class DailyTrafficStats:
    date_label: str
    total_bytes: int
    top_nodes: list[TrafficNodeUsage]


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
    devices_names: list[str] | None = None
    daily_traffic: DailyTrafficStats | None = None


def _bytes_to_gb(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{value / (1024 ** 3):.2f} GB"
    except Exception:
        return "—"


def _bytes_to_human(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        size = float(value)
    except Exception:
        return "—"

    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while abs(size) >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S")


def _format_devices(info: RemnawaveInfo) -> str:
    count = info.devices_count
    limit = info.devices_limit
    names = info.devices_names or []
    if count is None and limit is None:
        base = "—"
    elif count is not None and limit is not None:
        base = f"{count}/{limit}"
    elif limit is not None:
        base = str(limit)
    else:
        base = str(count)

    if not names:
        return base
    shown = names[:3]
    rest = len(names) - len(shown)
    suffix = f" … +{rest}" if rest > 0 else ""
    return f"{base} — {', '.join(shown)}{suffix}"


def _format_daily_traffic(stats: DailyTrafficStats | None) -> list[str]:
    if stats is None:
        return []

    lines = [
        "",
        hbold("📈 Трафик за сегодня"),
        f"🗓 День: {hcode(stats.date_label)} (МСК)",
        f"Σ Всего: {hcode(_bytes_to_human(stats.total_bytes))}",
    ]

    if stats.top_nodes:
        lines.append("Ноды:")
        for index, node in enumerate(stats.top_nodes, start=1):
            country = f"{node.country_code} · " if node.country_code else ""
            node_name = hcode(country + node.name)
            traffic = hcode(_bytes_to_human(node.total_bytes))
            lines.append(
                f"{index}. {node_name}: {traffic}"
            )

    return lines


def is_configured(config: RemnawaveConfig) -> bool:
    return bool(config.API_BASE and config.API_TOKEN)


def _int_or_zero(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _extract_daily_traffic_stats(stats: object, *, date_label: str) -> DailyTrafficStats | None:
    data = getattr(stats, "response", None) or getattr(stats, "root", None)
    if data is None:
        data = stats

    sparkline_data = getattr(data, "sparkline_data", None) or []
    top_nodes_raw = getattr(data, "top_nodes", None) or []
    series_raw = getattr(data, "series", None) or []

    total_bytes = sum(_int_or_zero(value) for value in sparkline_data)
    if total_bytes <= 0:
        total_bytes = sum(_int_or_zero(getattr(node, "total", None)) for node in top_nodes_raw)
    if total_bytes <= 0:
        total_bytes = sum(_int_or_zero(getattr(node, "total", None)) for node in series_raw)

    source_nodes = list(top_nodes_raw or series_raw)
    source_nodes.sort(key=lambda node: _int_or_zero(getattr(node, "total", None)), reverse=True)

    top_nodes: list[TrafficNodeUsage] = []
    for node in source_nodes:
        total = _int_or_zero(getattr(node, "total", None))
        if total <= 0:
            continue
        name = str(getattr(node, "name", None) or "Unknown")
        country_code = getattr(node, "country_code", None)
        top_nodes.append(
            TrafficNodeUsage(
                name=name,
                country_code=str(country_code).upper() if country_code else None,
                total_bytes=total,
            )
        )

    return DailyTrafficStats(
        date_label=date_label,
        total_bytes=total_bytes,
        top_nodes=top_nodes,
    )


async def _fetch_daily_traffic_stats(sdk: RemnawaveSDK, user_uuid: object) -> DailyTrafficStats | None:
    today = datetime.now(MSK).date()
    date_label = today.isoformat()
    try:
        stats = await sdk.bandwidthstats.get_stats_user_usage(
            str(user_uuid),
            top_nodes_limit=DAILY_TRAFFIC_NODES_LIMIT,
            start=date_label,
            end=date_label,
        )
    except Exception as exc:
        logger.warning("Failed to load daily traffic stats for %s: %s", user_uuid, exc)
        return None

    return _extract_daily_traffic_stats(stats, date_label=date_label)


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

        user_id = getattr(user, "id", None)
        if user_id is None:
            user_id = getattr(user, "user_id", None)
        if user_id is None:
            extra = getattr(user, "__pydantic_extra__", None) or getattr(user, "model_extra", None)
            if isinstance(extra, dict):
                user_id = extra.get("id") or extra.get("userId")

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
        devices_limit: Optional[int] = getattr(user, "hwid_device_limit", None)
        devices_names: list[str] = []
        if getattr(user, "uuid", None):
            try:
                devices = await sdk.hwid.get_hwid_user(str(user.uuid))
                devices_count = getattr(devices, "total", None)
                for device in getattr(devices, "devices", []) or []:
                    parts = []
                    model = getattr(device, "device_model", None)
                    platform = getattr(device, "platform", None)
                    os_version = getattr(device, "os_version", None)
                    if model:
                        parts.append(model)
                    elif platform:
                        parts.append(platform)
                    if os_version:
                        parts.append(os_version)
                    label = " ".join(parts).strip()
                    if not label:
                        label = (
                            getattr(device, "user_agent", None)
                            or getattr(device, "hwid", None)
                            or "Unknown"
                        )
                    devices_names.append(html.escape(str(label)))
            except Exception as exc:
                logger.warning("Failed to load HWID devices for %s: %s", user.uuid, exc)

        daily_traffic = None
        if getattr(user, "uuid", None):
            daily_traffic = await _fetch_daily_traffic_stats(sdk, user.uuid)

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
            devices_names=devices_names,
            daily_traffic=daily_traffic,
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
    elif "white" in internal_lower:
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
        f"🔗 Подписная ссылка: {hcode(info.subscription_url) if info.subscription_url else '—'}",
        f"🛰 Нода: {hcode(node)}",
        f"🕒 Последний онлайн: {_format_datetime(info.last_connected_at)}",
        f"🧩 Вид подписки: {subscription_kind}",
    ]

    if info.users_found > 1:
        lines.append(f"👥 Найдено пользователей по Telegram ID: {info.users_found}")

    lines.extend(_format_daily_traffic(info.daily_traffic))

    return "\n".join(lines)
