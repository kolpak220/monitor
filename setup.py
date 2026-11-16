from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import dotenv_values
from pyrogram import Client
from pyrogram.errors import PhoneCodeExpired, PhoneCodeInvalid, SessionPasswordNeeded

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DATA = ROOT / "data"


def ask(label, key, saved, secret=False, default=""):
    value = saved.get(key, default)
    hint = " [saved]" if secret and value else (f" [{value}]" if value else "")
    entered = input(f"{label}{hint}: ").strip()
    return entered or value


def explain_code_delivery(sent):
    delivery = type(sent.type).__name__
    descriptions = {
        "SentCodeTypeApp": "Telegram app (check the verified Telegram service chat on an already logged-in device)",
        "SentCodeTypeSms": "SMS text message",
        "SentCodeTypeCall": "automated phone call",
        "SentCodeTypeFlashCall": "missed-call verification",
        "SentCodeTypeMissedCall": "missed-call verification",
        "SentCodeTypeFragmentSms": "Fragment SMS",
        "SentCodeTypeFirebaseSms": "SMS verification",
    }
    print("\nTelegram accepted the login request.")
    print("Code delivery: " + descriptions.get(delivery, delivery))
    if getattr(sent, "next_type", None):
        print("Telegram may offer another delivery method after the current attempt.")
    print("The code comes from Telegram itself, NOT from this bot.")
    print("If no code arrives, check Telegram's service messages on your other devices.")
    print("You can type 'resend' at the code prompt to request another code.\n")


async def main():
    DATA.mkdir(exist_ok=True)
    saved = {k: str(v) for k, v in dotenv_values(ENV_FILE).items() if v is not None} if ENV_FILE.exists() else {}
    print("\nTelegram Username Monitor — local setup")
    print(f".env: {ENV_FILE}")
    print("Press Enter to reuse saved values.\n" if saved else "Enter your Telegram credentials.\n")

    api_id = ask("Telegram API ID", "TELEGRAM_API_ID", saved)
    api_hash = ask("Telegram API hash", "TELEGRAM_API_HASH", saved, True)
    phone = re.sub(r"\s+", "", ask("Phone number (+country code)", "PHONE_NUMBER", saved))
    token = ask("Bot token", "BOT_TOKEN", saved, True)
    admin = ask("Your numeric Telegram user ID", "ADMIN_USER_IDS", saved)
    if not api_id.isdigit() or not api_hash or not re.fullmatch(r"\+?[0-9]{7,16}", phone):
        raise SystemExit("Invalid API ID/hash or phone number.")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token):
        raise SystemExit("Bot token format is invalid.")
    if not admin.isdigit():
        raise SystemExit("Telegram user ID must be numeric.")

    kind = ask("Proxy type (none/socks5/http)", "PROXY_TYPE", saved, default="none").lower()
    if kind not in {"none", "socks5", "http"}:
        raise SystemExit("Proxy type must be none, socks5 or http.")
    host = port = username = password = ""
    proxy_url = None
    proxy = None
    if kind != "none":
        host = ask("Proxy host", "PROXY_HOST", saved)
        port = ask("Proxy port", "PROXY_PORT", saved)
        username = ask("Proxy username (optional)", "PROXY_USERNAME", saved)
        password = ask("Proxy password (optional)", "PROXY_PASSWORD", saved, True) if username else ""
        if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise SystemExit("Invalid proxy host or port.")
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
        proxy_url = f"{kind}://{auth}{host}:{port}"
        proxy = {"scheme": kind, "hostname": host, "port": int(port)}
        if username:
            proxy.update(username=username, password=password)

    session = AiohttpSession(proxy=proxy_url) if proxy_url else AiohttpSession()
    bot = Bot(token=token, session=session)
    try:
        me = await bot.get_me()
        print(f"Bot token valid: @{me.username or me.id}")
    finally:
        await bot.session.close()

    session_file = DATA / "userbot.session"
    reuse = session_file.exists() and input("Reuse saved Telegram user session? [Y/n]: ").strip().lower() not in {"n", "no"}
    if not reuse:
        client = Client("userbot", api_id=int(api_id), api_hash=api_hash, workdir=str(DATA), proxy=proxy)
        connected = False
        try:
            await client.connect()
            connected = True
            sent = await client.send_code(phone)
            explain_code_delivery(sent)
            while True:
                code = input("Code from Telegram (or 'resend'): ").strip()
                if not code:
                    print("Enter the code Telegram sent, or type 'resend'.")
                    continue
                if code.lower() == "resend":
                    sent = await client.resend_code(phone, sent.phone_code_hash)
                    explain_code_delivery(sent)
                    continue
                try:
                    await client.sign_in(phone, sent.phone_code_hash, code)
                    break
                except PhoneCodeInvalid:
                    print("Telegram rejected that code. Check the latest message and try again.")
                except PhoneCodeExpired:
                    print("That code expired. Requesting a fresh one...")
                    sent = await client.resend_code(phone, sent.phone_code_hash)
                    explain_code_delivery(sent)
                except SessionPasswordNeeded:
                    await client.check_password(input("Telegram two-step verification password: "))
                    break
            me = await client.get_me()
            print(f"Authorized user account: @{me.username or me.id}")
        finally:
            if connected:
                await client.disconnect()

    config = {
        "BOT_TOKEN": token, "TELEGRAM_API_ID": api_id, "TELEGRAM_API_HASH": api_hash,
        "PHONE_NUMBER": phone, "ADMIN_USER_IDS": admin,
        "PROXY_TYPE": "" if kind == "none" else kind, "PROXY_HOST": host, "PROXY_PORT": port,
        "PROXY_USERNAME": username, "PROXY_PASSWORD": password,
        "DEFAULT_INTERVAL_SECONDS": saved.get("DEFAULT_INTERVAL_SECONDS", "60"),
        "LOG_LEVEL": saved.get("LOG_LEVEL", "INFO"),
    }
    tmp = ENV_FILE.with_name(".env.tmp")
    tmp.write_text("# Local credentials; never commit this file.\n" +
                   "".join(f"{k}={json.dumps(v, ensure_ascii=False)}\n" for k, v in config.items()),
                   encoding="utf-8")
    os.replace(tmp, ENV_FILE)
    print(f"\nSaved {ENV_FILE}")
    print(f"SQLite database: {DATA / 'monitor.sqlite3'}")
    print("Start with: python main.py")


if __name__ == "__main__":
    asyncio.run(main())
