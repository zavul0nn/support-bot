from datetime import datetime, timezone

from app.bot.utils.remnawave import RemnawaveInfo, format_user_info


def test_format_user_info_contains_emojis_and_escapes():
    info = RemnawaveInfo(
        username="test_user",
        telegram_id=123,
        status="ACTIVE",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        expire_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        used_traffic_bytes=1024 ** 3,
        lifetime_traffic_bytes=2 * 1024 ** 3,
        last_connected_node_name="node-1",
        last_connected_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        internal_squads=["<alpha>", "beta"],
        external_squad="<ext>",
        users_found=2,
    )

    text = format_user_info(info, title="Remnawave: информация о пользователе")

    assert "👤" in text
    assert "🆔" in text
    assert "📶" in text
    assert "🛰" in text
    assert "🧩" in text
    assert "🧷" in text
    assert "👥" in text
    assert "&lt;alpha&gt;" in text
    assert "&lt;ext&gt;" in text
