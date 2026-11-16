from pathlib import Path

from monitor.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "bot_token": "token",
        "telegram_api_id": 1,
        "telegram_api_hash": "hash",
        "phone_number": "+10000000000",
        "admin_user_ids": (123,),
        "database_url": "postgresql+asyncpg://user:pass@host/db",
        "default_interval_seconds": 60,
        "check_poll_seconds": 3,
        "check_concurrency": 1,
        "notification_enabled": True,
        "log_level": "INFO",
        "proxy_type": "",
        "proxy_host": "",
        "proxy_port": None,
        "proxy_username": "",
        "proxy_password": "",
        "session_dir": Path("data/sessions"),
    }
    values.update(overrides)
    return Settings(**values)


def test_proxy_url_is_absent_without_proxy() -> None:
    assert make_settings().proxy_url is None


def test_proxy_url_quotes_credentials() -> None:
    settings = make_settings(
        proxy_type="socks5",
        proxy_host="127.0.0.1",
        proxy_port=1080,
        proxy_username="user name",
        proxy_password="p@ss",
    )
    assert settings.proxy_url == "socks5://user%20name:p%40ss@127.0.0.1:1080"


def test_kurigram_proxy_uses_shared_settings() -> None:
    settings = make_settings(proxy_type="http", proxy_host="proxy.local", proxy_port=8080)
    assert settings.kurigram_proxy == {
        "scheme": "http",
        "hostname": "proxy.local",
        "port": 8080,
    }
