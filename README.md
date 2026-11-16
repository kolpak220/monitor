# Telegram Username Monitor

A single-process local Python app. **No Docker, PostgreSQL, Redis, Alembic, or containers.** All monitoring data is stored in SQLite.

## Windows 10/11 setup

Install Python 3.13 and run in PowerShell from this folder. The project uses official Pyrogram (not Kurigram).

~~~powershell
if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
py -3.13 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python setup.py
python main.py
~~~

**Pyrogram compatibility note:** this project intentionally uses official Pyrogram 2.0.106. The upstream project is archived and no longer maintained, so Telegram API changes may eventually break login or MTProto requests.

The setup wizard creates `.env`, validates the bot token through the configured proxy, and starts the Pyrogram user client through that same proxy. On the first run, Pyrogram handles Telegram's interactive phone/code/two-step-password login and saves `data/userbot.session`. On later runs, press Enter to reuse that session. Keep the terminal open; stop with Ctrl+C and restart with `python main.py`.

A proxy is required. The same SOCKS5 or HTTP proxy is used for all Telegram network traffic: Bot API validation, bot polling, commands, notifications, and the Pyrogram MTProto user client. The `aiohttp-socks` dependency enables proxy support in aiogram.

## What it does

Monitors usernames for personal accounts, channels and supergroups. Default interval: 60 seconds per target. Results and the last 100 checks per target are stored in `data/monitor.sqlite3`. The bot sends notifications when a meaningful status changes and respects Telegram FloodWait responses.

**Availability warning:** Telegram does not guarantee that a username can be registered. “Apparently available” is an indication from Telegram's resolver, not a promise that registration or assignment will succeed. Auto-claim is opt-in per target and makes one attempt: it creates a channel titled with the username, then assigns the username. Another account may claim it first, Telegram may reject the assignment, and a failed assignment can leave an unassigned channel in your account. Re-arm with `/autoclaim @username` to try again.

## Commands

- `/start` — help
- `/add @username [user|channel|both]`
- `/remove @username`
- `/list`
- `/check @username`
- `/pause @username` / `/resume @username`
- `/autoclaim @username` — arm a one-shot attempt to create a channel titled with the username and assign it when Telegram reports it apparently available
- `/stopclaim @username` — disable auto-claim
- `/interval @username 60`
- `/history @username [count]`
- `/settings` / `/status`

Only the numeric ID in `ADMIN_USER_IDS` can use the bot. Open the bot and send `/start` once to enable notifications.

## Files and proxy

- `.env`: credentials and settings; never share or commit.
- `data/userbot.session`: logged-in Telegram session; treat it like a password.
- `data/monitor.sqlite3`: SQLite database; back up this file to preserve targets and history.

The proxy is mandatory and supports SOCKS5 or HTTP. All Telegram traffic uses it; there is no direct-connection fallback.
