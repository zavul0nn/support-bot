from datetime import datetime, timezone

from app.bot.utils.remnawave import (
    DailyTrafficStats,
    RemnawaveInfo,
    TrafficNodeUsage,
    format_user_info,
)


def test_format_user_info_contains_emojis_and_escapes():
    info = RemnawaveInfo(
        username="test_user",
        telegram_id=123,
        status="ACTIVE",
        user_id=42,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        expire_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        used_traffic_bytes=1024 ** 3,
        lifetime_traffic_bytes=2 * 1024 ** 3,
        last_connected_node_name="node-1",
        last_connected_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        subscription_url="https://example.com/sub",
        internal_squads=["<alpha>", "beta"],
        external_squad="<ext>",
        users_found=2,
        devices_count=1,
        devices_limit=3,
    )

    text = format_user_info(info, title="Remnawave: информация о пользователе")

    assert "👤" in text
    assert "🆔" in text
    assert "🔢" in text
    assert "📶" in text
    assert "🛰" in text
    assert "🧩" in text
    assert "👥" in text
    assert "🔗" in text
    assert "📱" in text
    assert "📱" in text
    assert "https://example.com/sub" in text
    assert "Вид подписки" in text
    assert "ПЛАТНАЯ" in text or "НИЩЕБРОД" in text or "&lt;alpha&gt;" in text


def test_format_user_info_includes_daily_traffic_stats():
    info = RemnawaveInfo(
        username="test_user",
        telegram_id=123,
        status="ACTIVE",
        user_id=42,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        expire_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        used_traffic_bytes=1024 ** 3,
        lifetime_traffic_bytes=2 * 1024 ** 3,
        last_connected_node_name="node-1",
        last_connected_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        subscription_url="https://example.com/sub",
        internal_squads=[],
        external_squad=None,
        daily_traffic=DailyTrafficStats(
            date_label="2026-05-13",
            total_bytes=(
                1024 ** 3
                + 512 * 1024 ** 2
                + 256 * 1024 ** 2
                + 128 * 1024 ** 2
            ),
            top_nodes=[
                TrafficNodeUsage(
                    name="<de-node>",
                    country_code="DE",
                    total_bytes=1024 ** 3,
                ),
                TrafficNodeUsage(
                    name="nl-node",
                    country_code="NL",
                    total_bytes=512 * 1024 ** 2,
                ),
                TrafficNodeUsage(
                    name="fr-node",
                    country_code="FR",
                    total_bytes=256 * 1024 ** 2,
                ),
                TrafficNodeUsage(
                    name="us-node",
                    country_code="US",
                    total_bytes=128 * 1024 ** 2,
                ),
            ],
        ),
    )

    text = format_user_info(info, title="Remnawave: информация о пользователе")

    assert "Трафик за сегодня" in text
    assert "2026-05-13" in text
    assert "1.88 GB" in text
    assert "512.00 MB" in text
    assert "&lt;de-node&gt;" in text
    assert "FR · fr-node" in text
    assert "US · us-node" in text


def test_format_user_info_includes_zero_daily_traffic():
    info = RemnawaveInfo(
        username="test_user",
        telegram_id=123,
        status="ACTIVE",
        user_id=42,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        expire_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        used_traffic_bytes=0,
        lifetime_traffic_bytes=0,
        last_connected_node_name=None,
        last_connected_at=None,
        subscription_url=None,
        internal_squads=[],
        external_squad=None,
        daily_traffic=DailyTrafficStats(
            date_label="2026-05-13",
            total_bytes=0,
            top_nodes=[],
        ),
    )

    text = format_user_info(info, title="Remnawave: информация о пользователе")

    assert "Трафик за сегодня" in text
    assert "0 B" in text
