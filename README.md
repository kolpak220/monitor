# Telegram Username Monitor

A self-hosted Telegram username monitor. Kurigram handles Telegram's MTProto API through a logged-in user account; aiogram provides a separate bot interface. Both use the same optional proxy configuration. Target data and check history are stored in PostgreSQL.

## What it does

- Monitors public usernames for **personal accounts and channels/supergroups**.
- Defaults to a 60-second interval per target. Intervals are independently configurable.
- Resolves exact usernames and performs a secondary Telegram username search.
- Records evidence, result history, errors and check timing.
- Sends notifications to configured administrator accounts when a meaningful result changes.
- Handles Telegram FloodWait responses without rapidly retrying.
- Persists targets, history and the user session across container restarts.

### Important availability limitation

Telegram does not provide a universal API that guarantees a username can be registered by any arbitrary account or channel. A failed exact resolution can indicate that no public entity is currently resolving under that name, but it is **not a registration guarantee**. The application therefore uses the label **Apparently available**, not “guaranteed available”. Collectible/purchase-available, invalid, occupied, inconclusive, rate-limited and error states are kept separate.

This tool monitors usernames explicitly added by its administrator. It does not enumerate arbitrary usernames or attempt to claim them.

## Requirements

- Docker Engine and Docker Compose v2.24 or newer.
- A Telegram account for the MTProto userbot.
- Telegram API ID and API hash from https://my.telegram.org.
- A bot token created with BotFather.
- Your numeric Telegram user ID for administrator access.

The bot token is created in BotFather. The setup wizard stores it locally; it cannot generate a Bot API token on your behalf.

## First-time setup

1. Clone this repository and open its directory.
2. The setup wizard creates the local environment file.
3. Run:

   ~~~sh
   docker compose --profile setup run --rm setup
   ~~~

4. Follow the prompts. The wizard asks for API credentials, phone number, login code, optional 2FA password, bot token, admin ID and one shared proxy configuration.
5. Start the services:

   ~~~sh
   docker compose up -d --build
   ~~~

6. Open your bot in Telegram and send /start.

The setup command must be run from an interactive terminal. The login code and 2FA password are entered interactively and are not written to the environment file.

### Shared proxy

The wizard accepts no proxy, SOCKS5 or HTTP. The selected proxy is passed to both the Kurigram MTProto client and aiogram Bot API session. The two clients still maintain independent connections.

## Bot commands

| Command | Description |
|---|---|
| /start | Open the dashboard |
| /add @username [user|channel] | Add a personal account, channel or supergroup username. Omit the type to monitor either type. |
| /remove @username | Remove a target and its retained history |
| /list | List monitored usernames |
| /check @username | Queue an immediate check |
| /pause @username | Pause a target |
| /resume @username | Resume a target |
| /interval @username 60 | Change an individual interval in seconds |
| /history @username | Show recent results |
| /settings | Show current defaults |
| /status | Show database and worker health |

Only Telegram IDs listed in ADMIN_USER_IDS can use the bot. Separate multiple administrator IDs with commas.

## Operations

View logs:

~~~sh
docker compose logs -f
docker compose logs -f userbot
docker compose logs -f bot
~~~

Restart services:

~~~sh
docker compose restart
~~~

Stop containers while preserving data:

~~~sh
docker compose down
~~~

To remove the PostgreSQL volume as well, use docker compose down -v. This permanently deletes monitoring data and history. The user session is stored in the local data/ directory, not in the PostgreSQL volume.

## Local files and secrets

- .env contains credentials and is ignored by Git.
- data/sessions/ contains the MTProto session and is ignored by Git.
- data/ is bind-mounted and survives container recreation.
- The setup wizard writes .env atomically, attempts to restrict its file permissions and gives the runtime container access to the session file.
- Do not share .env, session files, Telegram login codes or 2FA passwords.
- Never commit data/, .env or any copied session.

If a token or session is accidentally committed, deleting the file in a later commit does not remove it from Git history. Revoke the bot token with BotFather and terminate/revoke the Telegram session.

## Architecture

- bot: aiogram polling process and administrator interface.
- userbot: Kurigram MTProto client and polling scheduler.
- postgres: persistent relational storage, upgraded through Alembic migrations.
- Both Python services share the database and shared proxy settings, but run independently.
- The search registry keeps Telegram lookup strategies separate and combines their evidence before classification.

## Development and tests

Run tests locally with Python 3.11+:

~~~sh
python -m pip install -r requirements-dev.txt
PYTHONPATH=src pytest
ruff check src tests
~~~

The Docker image installs the application as a package. The Compose services do not mount the source tree, so local changes require a rebuild.

## Troubleshooting

- **Setup says the session is already authorized:** rerun setup and choose to reuse the existing session, or stop containers and intentionally remove data/sessions/ to authorize from scratch.
- **Userbot cannot connect:** check API ID/hash, shared proxy reachability and userbot logs.
- **Bot cannot connect:** check the bot token, shared proxy and bot logs.
- **FloodWait:** the worker backs off for the Telegram-provided duration. Avoid adding more targets or lowering intervals while Telegram is rate-limiting the account.
- **No notifications:** confirm your Telegram ID is configured, open the bot and press Start, and check notification settings and logs.

## Current scope

This is a first runnable implementation intended for local setup and testing. It deliberately uses conservative sequential checks by default. It does not claim registration availability, automatically acquire usernames, bypass Telegram rate limits or perform bulk enumeration.
