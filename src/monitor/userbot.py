from __future__ import annotations

import asyncio
import logging

from pyrogram import Client

from monitor.config import get_settings, validate_runtime_settings
from monitor.db import close_db, init_db
from monitor.scheduler import run_scheduler


async def main() -> None:
    settings = get_settings()
    validate_runtime_settings(settings)
    settings.session_dir.mkdir(parents=True, exist_ok=True)

    session_file = settings.session_dir / "userbot.session"
    if not session_file.exists():
        raise RuntimeError(
            "Kurigram session not found. Run 'docker compose --profile setup run --rm setup' first."
        )

    client = Client(
        name="userbot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        workdir=str(settings.session_dir),
        proxy=settings.kurigram_proxy,
    )

    await init_db()
    started = False
    try:
        await client.start()
        started = True
        me = await client.get_me()
        logging.getLogger(__name__).info(
            "Kurigram authorized as %s", getattr(me, "username", None) or me.id
        )
        await run_scheduler(client, settings)
    finally:
        if started:
            await client.stop()
        await close_db()


if __name__ == "__main__":
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
