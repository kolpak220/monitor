from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.raw.functions.contacts import ResolveUsername, Search

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / "monitor.sqlite3"
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("monitor")


def env(key, default=""):
    return os.getenv(key, default).strip()


def admins():
    try:
        return {int(x.strip()) for x in env("ADMIN_USER_IDS").split(",") if x.strip()}
    except ValueError as exc:
        raise RuntimeError("ADMIN_USER_IDS must contain numeric Telegram IDs.") from exc


def proxy_config():
    kind = env("PROXY_TYPE").lower()
    if not kind:
        return None, None
    if kind not in {"socks5", "http"}:
        raise RuntimeError("PROXY_TYPE must be socks5, http or empty.")
    host, port = env("PROXY_HOST"), env("PROXY_PORT")
    if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise RuntimeError("Invalid PROXY_HOST/PROXY_PORT.")
    user, password = env("PROXY_USERNAME"), os.getenv("PROXY_PASSWORD", "")
    auth = f"{quote(user, safe='')}:{quote(password, safe='')}@" if user else ""
    url = f"{kind}://{auth}{host}:{port}"
    raw = {"scheme": kind, "hostname": host, "port": int(port)}
    if user:
        raw.update(username=user, password=password)
    return url, raw


@contextmanager
def database():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_database():
    with database() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            target_type TEXT NOT NULL DEFAULT 'both', interval_seconds INTEGER NOT NULL DEFAULT 60,
            enabled INTEGER NOT NULL DEFAULT 1, last_status TEXT, last_checked REAL,
            next_check REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
            status TEXT NOT NULL, method TEXT NOT NULL, details TEXT NOT NULL,
            checked_at REAL NOT NULL, duration_ms INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS checks_target_time ON checks(target_id, checked_at DESC);
        CREATE INDEX IF NOT EXISTS targets_due ON targets(enabled, next_check);
        """)


def username_arg(value):
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    if not USERNAME_RE.fullmatch(value):
        raise ValueError("Username must be 5–32 characters, start with a letter, and contain only letters, digits or underscores.")
    return value.lower()


def status_label(status):
    return {
        "occupied": "Occupied",
        "apparently_available": "Apparently available (not guaranteed)",
        "collectible": "Collectible / purchase available",
        "invalid": "Invalid username",
        "inconclusive": "Inconclusive",
        "rate_limited": "Rate limited",
        "error": "Error",
    }.get(status or "", "Pending")


def classify(error):
    text = (str(getattr(error, "ID", "")) + " " + str(error)).upper()
    for marker, result in (
        ("USERNAME_PURCHASE_AVAILABLE", "collectible"),
        ("USERNAME_NOT_OCCUPIED", "apparently_available"),
        ("USERNAME_INVALID", "invalid"),
        ("USERNAME_OCCUPIED", "occupied"),
    ):
        if marker in text:
            return result
    return "inconclusive"


def resolved_type(response, kind):
    users = getattr(response, "users", []) or []
    chats = getattr(response, "chats", []) or []
    user = any(getattr(x, "username", None) for x in users)
    channel = any(getattr(x, "username", None) for x in chats)
    if kind == "user":
        return user
    if kind == "channel":
        return channel
    return user or channel


async def lookup(client, name, kind):
    try:
        response = await client.invoke(ResolveUsername(username=name))
        if resolved_type(response, kind):
            return "occupied", "contacts.resolveUsername", "Telegram resolved the exact username."
        return "inconclusive", "contacts.resolveUsername", "No matching entity in exact resolution response."
    except FloodWait:
        raise
    except Exception as exc:
        result = classify(exc)
        if result != "inconclusive":
            return result, "contacts.resolveUsername", f"Telegram returned {getattr(exc, 'ID', result)}."
        log.warning("Username lookup inconclusive (%s): %s", type(exc).__name__, getattr(exc, "ID", str(exc)))
        return result, "contacts.resolveUsername", f"Lookup inconclusive ({type(exc).__name__})."


async def secondary_lookup(client, name, kind):
    try:
        response = await client.invoke(Search(q=name, limit=20))
        expected = name.casefold()
        for item in getattr(response, "users", []) or []:
            if kind in {"both", "user"} and (getattr(item, "username", "") or "").casefold() == expected:
                return "occupied", "contacts.search", "Secondary search found exact personal account."
        for item in getattr(response, "chats", []) or []:
            if kind in {"both", "channel"} and (getattr(item, "username", "") or "").casefold() == expected:
                return "occupied", "contacts.search", "Secondary search found exact channel/supergroup."
        return "inconclusive", "contacts.search", "Secondary search found no exact match."
    except FloodWait:
        raise
    except Exception as exc:
        return "inconclusive", "contacts.search", f"Secondary search failed ({type(exc).__name__})."


def make_bot(token):
    # Bot API traffic is direct. The optional proxy belongs to the MTProto client only.
    return Bot(token=token, session=AiohttpSession())


async def check_one(client, bot, target):
    started = time.monotonic()
    name, kind = target["username"], target["target_type"]
    try:
        result, method, details = await lookup(client, name, kind)
        if result == "inconclusive":
            second = await secondary_lookup(client, name, kind)
            if second[0] == "occupied":
                result, method, details = second
        delay = target["interval_seconds"]
    except FloodWait as exc:
        delay = max(1, int(getattr(exc, "value", 0) or getattr(exc, "x", 0) or 60))
        result, method, details = "rate_limited", "telegram", f"Telegram FloodWait: retry after {delay}s."
    except Exception as exc:
        delay = min(1800, max(10, target["interval_seconds"]) * 2)
        result, method, details = "error", "worker", f"{type(exc).__name__}: {exc}"

    now = time.time()
    with database() as con:
        con.execute("INSERT INTO checks(target_id,status,method,details,checked_at,duration_ms) VALUES(?,?,?,?,?,?)",
                    (target["id"], result, method, details, now, int((time.monotonic()-started)*1000)))
        con.execute("UPDATE targets SET last_status=?,last_checked=?,next_check=? WHERE id=?",
                    (result, now, now + delay, target["id"]))
        con.execute("""DELETE FROM checks WHERE target_id=? AND id NOT IN
                       (SELECT id FROM checks WHERE target_id=? ORDER BY checked_at DESC LIMIT 100)""",
                    (target["id"], target["id"]))
    log.info("@%s: %s", name, result)

    notifyable = {"occupied", "apparently_available", "collectible", "invalid"}
    if result in notifyable and result != target["last_status"]:
        for admin_id in admins():
            try:
                await bot.send_message(admin_id, f"Username update: @{name}\n"
                    f"{status_label(target['last_status'])} → {status_label(result)}\n{details}")
            except Exception:
                log.exception("Notification to admin %s failed", admin_id)


async def scheduler(client, bot, stop):
    while not stop.is_set():
        with database() as con:
            target = con.execute(
                "SELECT * FROM targets WHERE enabled=1 AND next_check<=? ORDER BY next_check,id LIMIT 1",
                (time.time(),)
            ).fetchone()
        if target is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
            continue
        await check_one(client, bot, target)


def register_handlers(dp, default_interval):
    def protected(handler):
        async def wrapper(message: Message):
            if not message.from_user or message.from_user.id not in admins():
                await message.answer("Access denied.")
                return
            await handler(message)
        return wrapper

    @dp.message(Command("start", "help"))
    @protected
    async def start(message):
        await message.answer(
            "Username Monitor\n\n"
            "/add @name [user|channel|both]\n/remove @name\n/list\n"
            "/check @name\n/pause @name\n/resume @name\n"
            "/interval @name seconds\n/history @name [count]\n/settings\n/status"
        )

    @dp.message(Command("add"))
    @protected
    async def add(message):
        parts = (message.text or "").split()
        if len(parts) not in (2, 3):
            return await message.answer("Usage: /add @username [user|channel|both]")
        try:
            name = username_arg(parts[1])
        except ValueError as exc:
            return await message.answer(str(exc))
        kind = parts[2].lower() if len(parts) == 3 else "both"
        if kind not in {"user", "channel", "both"}:
            return await message.answer("Type must be user, channel or both.")
        with database() as con:
            try:
                con.execute("INSERT INTO targets(username,target_type,interval_seconds,created_at,next_check) VALUES(?,?,?,?,0)",
                            (name, kind, default_interval, time.time()))
            except sqlite3.IntegrityError:
                return await message.answer(f"@{name} is already monitored.")
        await message.answer(f"Added @{name} ({kind}), interval {default_interval}s.")

    @dp.message(Command("remove"))
    @protected
    async def remove(message):
        parts = (message.text or "").split()
        if len(parts) != 2:
            return await message.answer("Usage: /remove @username")
        try:
            name = username_arg(parts[1])
        except ValueError as exc:
            return await message.answer(str(exc))
        with database() as con:
            cur = con.execute("DELETE FROM targets WHERE username=?", (name,))
        await message.answer(f"Removed @{name}." if cur.rowcount else f"@{name} not found.")

    @dp.message(Command("list"))
    @protected
    async def list_targets(message):
        with database() as con:
            rows = con.execute("SELECT * FROM targets ORDER BY username").fetchall()
        if not rows:
            return await message.answer("No targets. Add one with /add @username.")
        lines = [f"• @{r['username']} — {'active' if r['enabled'] else 'paused'} — {status_label(r['last_status'])} — {r['interval_seconds']}s" for r in rows]
        await message.answer("Monitored usernames:\n" + "\n".join(lines))

    @dp.message(Command("pause", "resume", "check"))
    @protected
    async def target_action(message):
        command = (message.text or "").split()[0].split("@")[0].lower()
        parts = (message.text or "").split()
        if len(parts) != 2:
            return await message.answer(f"Usage: {command} @username")
        try:
            name = username_arg(parts[1])
        except ValueError as exc:
            return await message.answer(str(exc))
        with database() as con:
            row = con.execute("SELECT id FROM targets WHERE username=?", (name,)).fetchone()
            if row:
                if command == "/check":
                    con.execute("UPDATE targets SET next_check=0 WHERE id=?", (row["id"],))
                else:
                    con.execute("UPDATE targets SET enabled=? WHERE id=?", (command == "/resume", row["id"]))
        if not row:
            return await message.answer(f"@{name} is not monitored.")
        await message.answer(f"Queued check for @{name}." if command == "/check" else f"@{name} {'resumed' if command == '/resume' else 'paused'}.")

    @dp.message(Command("interval"))
    @protected
    async def interval(message):
        parts = (message.text or "").split()
        if len(parts) != 3:
            return await message.answer("Usage: /interval @username seconds")
        try:
            name, seconds = username_arg(parts[1]), int(parts[2])
            if not 10 <= seconds <= 86400:
                raise ValueError("Interval must be between 10 and 86400 seconds.")
        except ValueError as exc:
            return await message.answer(str(exc))
        with database() as con:
            cur = con.execute("UPDATE targets SET interval_seconds=?,next_check=0 WHERE username=?", (seconds, name))
        await message.answer(f"Updated @{name}: {seconds}s." if cur.rowcount else f"@{name} not found.")

    @dp.message(Command("history"))
    @protected
    async def history(message):
        parts = (message.text or "").split()
        if len(parts) not in (2, 3):
            return await message.answer("Usage: /history @username [count]")
        try:
            name = username_arg(parts[1])
            count = min(20, max(1, int(parts[2]))) if len(parts) == 3 else 10
        except ValueError as exc:
            return await message.answer(str(exc))
        with database() as con:
            rows = con.execute("SELECT c.* FROM checks c JOIN targets t ON t.id=c.target_id WHERE t.username=? ORDER BY c.checked_at DESC LIMIT ?", (name, count)).fetchall()
        if not rows:
            return await message.answer("No history recorded.")
        lines = [f"Recent checks for @{name}:"]
        for row in rows:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(row["checked_at"]))
            lines.append(f"• {stamp} — {status_label(row['status'])} — {row['method']}")
        await message.answer("\n".join(lines))

    @dp.message(Command("settings"))
    @protected
    async def settings(message):
        await message.answer(f"SQLite: {DB_PATH}\nDefault interval: {default_interval}s\nProxy: {env('PROXY_TYPE') or 'disabled'}")

    @dp.message(Command("status"))
    @protected
    async def status(message):
        with database() as con:
            total = con.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
            active = con.execute("SELECT COUNT(*) FROM targets WHERE enabled=1").fetchone()[0]
        await message.answer(f"Bot: online\nUser session: connected\nTargets: {active}/{total}\nStorage: SQLite")


async def main():
    token, api_id, api_hash = env("BOT_TOKEN"), env("TELEGRAM_API_ID"), env("TELEGRAM_API_HASH")
    if not token or not api_id.isdigit() or not api_hash or not admins():
        raise RuntimeError("Configuration missing. Run python setup.py first.")
    _, proxy = proxy_config()
    if not (DATA / "userbot.session").exists():
        raise RuntimeError("Telegram user session missing. Run python setup.py first.")
    default_interval = max(10, int(env("DEFAULT_INTERVAL_SECONDS", "60")))
    init_database()
    user = Client("userbot", api_id=int(api_id), api_hash=api_hash, workdir=str(DATA), proxy=proxy)
    bot = make_bot(token)
    dp = Dispatcher()
    register_handlers(dp, default_interval)
    await user.start()
    me = await user.get_me()
    log.info("MTProto session connected: %s", getattr(me, "username", None) or me.id)
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler(user, bot, stop))
    try:
        await dp.start_polling(bot)
    finally:
        stop.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await user.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
