from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from sqlalchemy.ext.asyncio import AsyncSession

from monitor.config import Settings
from monitor.models import Notification, Target

logger = logging.getLogger(__name__)


def build_bot(settings: Settings) -> Bot:
    session = AiohttpSession(proxy=settings.proxy_url)
    return Bot(token=settings.bot_token, session=session)


async def notify_status_change(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    target: Target,
    old_status: str | None,
    new_status: str,
    details: str,
) -> None:
    notification = Notification(
        target_id=target.id,
        username=target.username,
        old_status=old_status,
        new_status=new_status,
    )
    session.add(notification)
    await session.flush()

    if not settings.notification_enabled:
        notification.error = "Notifications are disabled in configuration."
        return

    message = (
        f"Username status changed: @{target.username}\n"
        f"{old_status or 'not checked'} → {new_status}\n\n"
        f"{details}"
    )
    failures: list[str] = []
    for admin_id in settings.admin_user_ids:
        try:
            await bot.send_message(admin_id, message)
        except Exception as error:
            logger.warning(
                "Notification delivery failed for admin %s: %s",
                admin_id,
                type(error).__name__,
            )
            failures.append(type(error).__name__)

    if failures:
        notification.error = ", ".join(failures)
    else:
        notification.sent_at = datetime.now(timezone.utc)
