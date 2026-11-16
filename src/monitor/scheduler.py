from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitor.config import Settings
from monitor.db import SessionFactory
from monitor.domain import RateLimitedError, ResultStatus, TargetType
from monitor.models import CheckResult, ServiceHeartbeat, Target
from monitor.notifications import build_bot, notify_status_change
from monitor.search.registry import build_registry

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _target_type(value: str) -> TargetType:
    try:
        return TargetType(value)
    except ValueError:
        return TargetType.BOTH


async def _heartbeat(session: AsyncSession) -> None:
    heartbeat = await session.get(ServiceHeartbeat, "userbot")
    if heartbeat is None:
        session.add(
            ServiceHeartbeat(service="userbot", last_seen_at=now_utc(), details="running")
        )
    else:
        heartbeat.last_seen_at = now_utc()
        heartbeat.details = "running"


async def _check_one(client, target_id: int, settings: Settings, registry, bot) -> None:
    started = time.monotonic()
    async with SessionFactory() as session:
        target = await session.get(Target, target_id)
        if target is None or not target.enabled:
            return

        previous_status = target.last_status
        try:
            evidence = await registry.check(
                client,
                target.username,
                _target_type(target.target_type),
            )
            duration = int((time.monotonic() - started) * 1000)
            checked_at = now_utc()
            session.add(
                CheckResult(
                    target_id=target.id,
                    status=evidence.status.value,
                    method=evidence.method,
                    details=evidence.details,
                    checked_at=checked_at,
                    duration_ms=duration,
                )
            )
            target.last_checked_at = checked_at
            target.next_check_at = checked_at + timedelta(seconds=target.interval_seconds)
            target.consecutive_errors = 0
            target.last_status = evidence.status.value

            notifyable = {
                ResultStatus.OCCUPIED,
                ResultStatus.APPARENTLY_AVAILABLE,
                ResultStatus.COLLECTIBLE,
                ResultStatus.INVALID,
            }
            if evidence.status in notifyable and previous_status != evidence.status.value:
                await notify_status_change(
                    session,
                    bot,
                    settings,
                    target,
                    previous_status,
                    evidence.status.value,
                    evidence.details,
                )
            await session.commit()
            logger.info("Checked @%s: %s (%s ms)", target.username, evidence.status.value, duration)

        except RateLimitedError as error:
            checked_at = now_utc()
            target.last_checked_at = checked_at
            target.next_check_at = checked_at + timedelta(seconds=error.seconds)
            target.consecutive_errors += 1
            session.add(
                CheckResult(
                    target_id=target.id,
                    status=ResultStatus.RATE_LIMITED.value,
                    method="telegram",
                    details=f"Telegram requested a retry after {error.seconds} seconds.",
                    checked_at=checked_at,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            await session.commit()
            logger.warning(
                "FloodWait while checking @%s; retry in %s seconds",
                target.username,
                error.seconds,
            )

        except Exception as error:
            checked_at = now_utc()
            target.last_checked_at = checked_at
            target.consecutive_errors += 1
            delay = min(
                1800,
                max(5, target.interval_seconds)
                * (2 ** min(target.consecutive_errors - 1, 5)),
            )
            target.next_check_at = checked_at + timedelta(seconds=delay)
            session.add(
                CheckResult(
                    target_id=target.id,
                    status=ResultStatus.ERROR.value,
                    method="worker",
                    details=f"Unexpected {type(error).__name__}; retry scheduled in {delay} seconds.",
                    checked_at=checked_at,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            await session.commit()
            logger.exception("Unexpected monitoring error for @%s", target.username)


async def run_scheduler(client, settings: Settings) -> None:
    registry = build_registry()
    bot = build_bot(settings)
    semaphore = asyncio.Semaphore(settings.check_concurrency)
    try:
        async with bot:
            while True:
                async with SessionFactory() as session:
                    await _heartbeat(session)
                    await session.commit()
                    due_ids = list(
                        await session.scalars(
                            select(Target.id)
                            .where(
                                Target.enabled.is_(True),
                                (Target.next_check_at.is_(None))
                                | (Target.next_check_at <= now_utc()),
                            )
                            .order_by(Target.next_check_at.asc().nullsfirst(), Target.id.asc())
                            .limit(settings.check_concurrency)
                        )
                    )

                if due_ids:
                    async def run_limited(target_id: int) -> None:
                        async with semaphore:
                            await _check_one(client, target_id, settings, registry, bot)

                    await asyncio.gather(*(run_limited(target_id) for target_id in due_ids))
                else:
                    await asyncio.sleep(settings.check_poll_seconds)
    finally:
        await bot.session.close()
