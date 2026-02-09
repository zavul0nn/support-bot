from app.config import load_config


def test_load_config_defaults_include_remnawave() -> None:
    config = load_config()
    assert config.remnawave.API_BASE == ""
    assert config.remnawave.API_TOKEN == ""
    assert config.remnawave.CADDY_TOKEN is None
    assert config.remnawave.SSL_IGNORE is False
