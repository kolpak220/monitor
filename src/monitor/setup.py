from __future__ import annotations

import asyncio
import getpass
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded

ENV_PATH = Path(os.getenv("SETUP_ENV_PATH", ".env"))
SESSION_DIR = Path(os.getenv("SESSION_DIR", "data/sessions"))


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_secret(prompt: str) -> str:
    return getpass.getpass(f"{prompt}: ").strip()


def _dotenv_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _proxy_url(kind: str, host: str, port: int, username: str, password: str) -> str | None:
    if not kind:
        return None
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    return f"{kind}://{auth}{host}:{port}"


async def validate_bot_token(token: str, proxy_url: str | None) -> str:
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=token, session=session)
    try:
        me = await bot.get_me()
        return f"@{me.username}" if me.username else str(me.id)
    finally:
        await bot.session.close()


async def authorize_userbot(api_id: int, api_hash: str, phone: str, proxy: dict | None) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    client = Client(
        name="userbot",
        api_id=api_id,
        api_hash=api_hash,
        workdir=str(SESSION_DIR),
        proxy=proxy,
    )
    connected = False
    try:
        await client.connect()
        connected = True
        sent_code = await client.send_code(phone)
        code = ask_secret("Telegram login code")
        try:
            await client.sign_in(phone, sent_code.phone_code_hash, code)
        except SessionPasswordNeeded:
            password = ask_secret("Telegram two-step verification password")
            await client.check_password(password)
        me = await client.get_me()
        print(f"User session authorized as {getattr(me, 'username', None) or me.id}.")
    finally:
        if connected:
            await client.disconnect()


def _set_runtime_permissions(env_path: Path, session_dir: Path) -> None:
    try:
        parent_stat = env_path.parent.stat()
        host_uid = int(os.getenv("LOCAL_UID", str(parent_stat.st_uid)))
        host_gid = int(os.getenv("LOCAL_GID", str(parent_stat.st_gid)))
        os.chown(env_path, host_uid, host_gid)
        os.chmod(env_path, 0o600)
    except (OSError, ValueError):
        pass

    try:
        os.chown(session_dir, 10001, 10001)
        os.chmod(session_dir, 0o700)
        for item in session_dir.iterdir():
            if item.is_file():
                os.chown(item, 10001, 10001)
                os.chmod(item, 0o600)
    except OSError:
        pass


async def main() -> None:
    print("\nTelegram Username Monitor — local setup\n")
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Setup requires an interactive terminal. "
            "Run with docker compose --profile setup run --rm -it setup."
        )

    if ENV_PATH.exists():
        replace = ask("An .env file already exists. Replace it? (y/N)", "N").lower()
        if replace not in {"y", "yes"}:
            print("Existing configuration left unchanged.")
            return

    api_id_raw = ask("Telegram API ID")
    if not api_id_raw.isdigit():
        raise ValueError("Telegram API ID must be numeric.")
    api_id = int(api_id_raw)
    api_hash = ask_secret("Telegram API hash")
    if not api_hash:
        raise ValueError("Telegram API hash cannot be empty.")
    phone = re.sub(r"\s+", "", ask("Phone number, including country code"))
    if not re.fullmatch(r"\+?[0-9]{7,16}", phone):
        raise ValueError("Enter a valid phone number with country code.")

    bot_token = ask_secret("Bot token from BotFather")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", bot_token):
        raise ValueError("Bot token does not look valid.")

    admin_ids_raw = ask("Your numeric Telegram user ID")
    if not admin_ids_raw.isdigit():
        raise ValueError("Administrator ID must be numeric.")

    proxy_type = ask("Shared proxy type (none/socks5/http)", "none").lower()
    if proxy_type not in {"none", "socks5", "http"}:
        raise ValueError("Proxy type must be none, socks5 or http.")

    proxy = None
    proxy_kind = ""
    proxy_host = ""
    proxy_port = 0
    proxy_username = ""
    proxy_password = ""
    if proxy_type != "none":
        proxy_kind = proxy_type
        proxy_host = ask("Proxy host")
        if not proxy_host:
            raise ValueError("Proxy host cannot be empty.")
        proxy_port_raw = ask("Proxy port")
        if not proxy_port_raw.isdigit() or not (1 <= int(proxy_port_raw) <= 65535):
            raise ValueError("Proxy port must be between 1 and 65535.")
        proxy_port = int(proxy_port_raw)
        proxy_username = ask("Proxy username (leave empty if not required)")
        proxy_password = ask_secret("Proxy password") if proxy_username else ""
        proxy = {
            "scheme": proxy_kind,
            "hostname": proxy_host,
            "port": proxy_port,
        }
        if proxy_username:
            proxy["username"] = proxy_username
            proxy["password"] = proxy_password

    proxy_url = (
        _proxy_url(proxy_kind, proxy_host, proxy_port, proxy_username, proxy_password)
        if proxy_kind
        else None
    )

    print("\nValidating bot token through the configured shared proxy...")
    bot_username = await validate_bot_token(bot_token, proxy_url)
    print(f"Bot token valid: {bot_username}")

    session_file = SESSION_DIR / "userbot.session"
    reuse = False
    if session_file.exists():
        reuse = ask(
            "An existing userbot session was found. Reuse it? (Y/n)", "Y"
        ).lower() not in {"n", "no"}
    if not reuse:
        print("\nTelegram will send a login code to your account.")
        await authorize_userbot(api_id, api_hash, phone, proxy)
    else:
        print("Existing session will be reused. The userbot will validate it on startup.")

    values = {
        "BOT_TOKEN": bot_token,
        "TELEGRAM_API_ID": str(api_id),
        "TELEGRAM_API_HASH": api_hash,
        "PHONE_NUMBER": phone,
        "ADMIN_USER_IDS": admin_ids_raw,
        "PROXY_TYPE": proxy_kind,
        "PROXY_HOST": proxy_host,
        "PROXY_PORT": str(proxy_port) if proxy_kind else "",
        "PROXY_USERNAME": proxy_username,
        "PROXY_PASSWORD": proxy_password,
        "DATABASE_URL": "postgresql+asyncpg://monitor:monitor@postgres:5432/monitor",
        "DEFAULT_INTERVAL_SECONDS": "60",
        "CHECK_POLL_SECONDS": "3",
        "CHECK_CONCURRENCY": "1",
        "NOTIFICATION_ENABLED": "true",
        "LOG_LEVEL": "INFO",
    }
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ENV_PATH.with_name(ENV_PATH.name + ".tmp")
    temporary.write_text(
        "# Generated locally by monitor.setup. Do not commit this file.\n"
        + "".join(f"{key}={_dotenv_value(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    os.replace(temporary, ENV_PATH)
    _set_runtime_permissions(ENV_PATH, SESSION_DIR)
    print(f"\nConfiguration saved to {ENV_PATH}.")
    print(f"Userbot session saved under {SESSION_DIR}.")
    print("Start the application with: docker compose up -d --build")


if __name__ == "__main__":
    asyncio.run(main())
