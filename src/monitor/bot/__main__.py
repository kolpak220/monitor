from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher
from aiogram.types import BotCommand

from monitor.bot.filters import AdminFilter
from monitor.bot.handlers import router
from monitor.config import get_settings, validate_runtime_settings
from monitor.db import close_db, init_db
from monitor.notifications import build_bot


async def main() -> None:
    settings = get_settings()
    validate_runtime_settings(settings)
    if not settings.admin_user_ids:
        raise RuntimeError("Configure ADMIN_USER_IDS before starting the bot.")

    await init_db()
    bot = build_bot(settings)
    dispatcher = Dispatcher()
    router.message.filter(AdminFilter(settings.admin_user_ids))
    router.callback_query.filter(AdminFilter(settings.admin_user_ids))
    dispatcher.include_router(router)

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Open dashboard"),
                BotCommand(command="add", description="Add a username"),
                BotCommand(command="remove", description="Remove a username"),
                BotCommand(command="list", description="List monitored usernames"),
                BotCommand(command="check", description="Queue an immediate check"),
                BotCommand(command="pause", description="Pause a target"),
                BotCommand(command="resume", description="Resume a target"),
                BotCommand(command="interval", description="Change target interval"),
                BotCommand(command="history", description="View check history"),
                BotCommand(command="settings", description="Show settings"),
                BotCommand(command="status", description="Show service health"),
            ]
        )
        logging.getLogger(__name__).info("Bot polling started")
        await dispatcher.start_polling(bot, settings=settings)
    finally:
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
