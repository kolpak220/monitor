from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    telegram_api_id: int
    telegram_api_hash: str
    phone_number: str
    admin_user_ids: tuple[int, ...]
    database_url: str
    default_interval_seconds: int
    check_poll_seconds: int
    check_concurrency: int
    notification_enabled: bool
    log_level: str
    proxy_type: str
    proxy_host: str
    proxy_port: int | None
    proxy_username: str
    proxy_password: str
    session_dir: Path

    @property
    def proxy_url(self) -> str | None:
        if not self.proxy_type:
            return None
        auth = ""
        if self.proxy_username:
            auth = (
                f"{quote(self.proxy_username, safe='')}:"
                f"{quote(self.proxy_password, safe='')}@"
            )
        return f"{self.proxy_type}://{auth}{self.proxy_host}:{self.proxy_port}"

    @property
    def kurigram_proxy(self) -> dict[str, str | int] | None:
        if not self.proxy_type:
            return None
        proxy: dict[str, str | int] = {
            "scheme": self.proxy_type,
            "hostname": self.proxy_host,
            "port": int(self.proxy_port or 0),
        }
        if self.proxy_username:
            proxy["username"] = self.proxy_username
            proxy["password"] = self.proxy_password
        return proxy


def get_settings() -> Settings:
    raw_admins = os.getenv("ADMIN_USER_IDS", "")
    admin_ids: list[int] = []
    for item in raw_admins.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            admin_ids.append(int(item))
        except ValueError as exc:
            raise ValueError("ADMIN_USER_IDS must be comma-separated numeric Telegram IDs") from exc

    proxy_type = os.getenv("PROXY_TYPE", "").strip().lower()
    if proxy_type not in {"", "socks5", "http"}:
        raise ValueError("PROXY_TYPE must be empty, socks5 or http")

    proxy_port = _int_env("PROXY_PORT", 0) if proxy_type else None
    if proxy_type and not (1 <= int(proxy_port or 0) <= 65535):
        raise ValueError("PROXY_PORT must be between 1 and 65535 when a proxy is enabled")

    interval = _int_env("DEFAULT_INTERVAL_SECONDS", 60)
    if interval < 10:
        raise ValueError("DEFAULT_INTERVAL_SECONDS must be at least 10 seconds")

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        telegram_api_id=_int_env("TELEGRAM_API_ID", 0),
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH", "").strip(),
        phone_number=os.getenv("PHONE_NUMBER", "").strip(),
        admin_user_ids=tuple(admin_ids),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://monitor:monitor@postgres:5432/monitor",
        ).strip(),
        default_interval_seconds=interval,
        check_poll_seconds=max(1, _int_env("CHECK_POLL_SECONDS", 3)),
        check_concurrency=max(1, _int_env("CHECK_CONCURRENCY", 1)),
        notification_enabled=_bool_env("NOTIFICATION_ENABLED", True),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        proxy_type=proxy_type,
        proxy_host=os.getenv("PROXY_HOST", "").strip(),
        proxy_port=proxy_port,
        proxy_username=os.getenv("PROXY_USERNAME", ""),
        proxy_password=os.getenv("PROXY_PASSWORD", ""),
        session_dir=Path(os.getenv("SESSION_DIR", "/data/sessions")),
    )


def validate_runtime_settings(settings: Settings) -> None:
    missing = []
    if not settings.bot_token:
        missing.append("BOT_TOKEN")
    if not settings.telegram_api_id:
        missing.append("TELEGRAM_API_ID")
    if not settings.telegram_api_hash:
        missing.append("TELEGRAM_API_HASH")
    if not settings.admin_user_ids:
        missing.append("ADMIN_USER_IDS")
    if settings.proxy_type and not settings.proxy_host:
        missing.append("PROXY_HOST")
    if missing:
        raise RuntimeError(
            "Missing configuration: "
            + ", ".join(missing)
            + ". Run 'docker compose --profile setup run --rm setup' first."
        )
