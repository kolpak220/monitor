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

The setup wizard creates `.env`, validates the bot token, and logs in the Telegram user account once. On later runs press Enter to keep saved settings and reuse the session. Keep the terminal open; stop with Ctrl+C and restart with `python main.py`.

## What it does

Monitors usernames for personal accounts, channels and supergroups. Default interval: 60 seconds per target. Results and the last 100 checks per target are stored in `data/monitor.sqlite3`. The bot sends notifications when a meaningful status changes and respects Telegram FloodWait responses.

**Availability warning:** Telegram does not guarantee that a username can be registered. “Apparently available” is an indication from Telegram's resolver, not a promise that registration or assignment will succeed.

## Commands

- `/start` — help
- `/add @username [user|channel|both]`
- `/remove @username`
- `/list`
- `/check @username`
- `/pause @username` / `/resume @username`
- `/interval @username 60`
- `/history @username [count]`
- `/settings` / `/status`

Only the numeric ID in `ADMIN_USER_IDS` can use the bot. Open the bot and send `/start` once to enable notifications.

## Files and proxy

- `.env`: credentials and settings; never share or commit.
- `data/userbot.session`: logged-in Telegram session; treat it like a password.
- `data/monitor.sqlite3`: SQLite database; back up this file to preserve targets and history.

Optional proxy supports SOCKS5 or HTTP and is shared by the MTProto user client and Bot API client. Leave proxy type as `none` to connect directly.
