from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, func, select

from monitor.config import Settings
from monitor.db import SessionFactory
from monitor.domain import TargetType, validate_username
from monitor.models import CheckResult, ServiceHeartbeat, Target
from monitor.bot.keyboards import dashboard_keyboard

router = Router()


def _target_type(value: str | None) -> str:
    if value is None:
        return TargetType.BOTH.value
    normalized = value.lower()
    if normalized in {"user", "account", "personal"}:
        return TargetType.USER.value
    if normalized in {"channel", "group", "supergroup"}:
        return TargetType.CHANNEL.value
    return TargetType.BOTH.value


async def _get_target(session, username: str) -> Target | None:
    return await session.scalar(select(Target).where(Target.username == username))


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Telegram Username Monitor\n\n"
        "Monitor public usernames for personal accounts and channels/supergroups.\n"
        "Default interval: 60 seconds per target.\n\n"
        "Use /add @username to start monitoring, or open the dashboard below.",
        reply_markup=dashboard_keyboard(),
    )


@router.message(Command("add"))
async def add_target(message: Message, settings: Settings) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or len(parts) > 3:
        await message.answer("Usage: /add @username [user|channel]")
        return
    try:
        username = validate_username(parts[1])
    except ValueError as error:
        await message.answer(str(error))
        return

    if len(parts) == 3 and parts[2].lower() not in {
        "user", "account", "personal", "channel", "group", "supergroup", "both"
    }:
        await message.answer("Target type must be user, channel or both.")
        return

    kind = _target_type(parts[2] if len(parts) > 2 else None)
    async with SessionFactory() as session:
        existing = await _get_target(session, username)
        if existing:
            existing.enabled = True
            existing.target_type = kind
            existing.next_check_at = datetime.now(timezone.utc)
            await session.commit()
            await message.answer(f"@{username} is already registered; monitoring has been resumed.")
            return
        target = Target(
            username=username,
            target_type=kind,
            enabled=True,
            interval_seconds=settings.default_interval_seconds,
            next_check_at=datetime.now(timezone.utc),
        )
        session.add(target)
        await session.commit()
    await message.answer(
        f"Added @{username} ({kind}). First check is queued. "
        f"Interval: {settings.default_interval_seconds} seconds."
    )


@router.message(Command("remove"))
async def remove_target(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Usage: /remove @username")
        return
    try:
        username = validate_username(parts[1])
    except ValueError as error:
        await message.answer(str(error))
        return
    async with SessionFactory() as session:
        target = await _get_target(session, username)
        if target is None:
            await message.answer(f"@{username} is not being monitored.")
            return
        await session.delete(target)
        await session.commit()
    await message.answer(f"Removed @{username} and its check history.")


@router.message(Command("list"))
async def list_targets(message: Message) -> None:
    async with SessionFactory() as session:
        targets = list(await session.scalars(select(Target).order_by(Target.username.asc())))
    if not targets:
        await message.answer("No usernames are being monitored. Use /add @username.")
        return
    lines = ["Monitored usernames:"]
    for target in targets:
        state = "active" if target.enabled else "paused"
        status = target.last_status or "pending"
        lines.append(
            f"• @{target.username} — {state} — {target.target_type} — "
            f"{target.interval_seconds}s — {status}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("check"))
async def check_target(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Usage: /check @username")
        return
    try:
        username = validate_username(parts[1])
    except ValueError as error:
        await message.answer(str(error))
        return
    async with SessionFactory() as session:
        target = await _get_target(session, username)
        if target is None:
            await message.answer(f"@{username} is not being monitored.")
            return
        target.enabled = True
        target.next_check_at = datetime.now(timezone.utc)
        await session.commit()
    await message.answer(f"An immediate check for @{username} has been queued.")


async def _set_enabled(message: Message, enabled: bool) -> None:
    parts = (message.text or "").split()
    command = "resume" if enabled else "pause"
    if len(parts) != 2:
        await message.answer(f"Usage: /{command} @username")
        return
    try:
        username = validate_username(parts[1])
    except ValueError as error:
        await message.answer(str(error))
        return
    async with SessionFactory() as session:
        target = await _get_target(session, username)
        if target is None:
            await message.answer(f"@{username} is not being monitored.")
            return
        target.enabled = enabled
        if enabled:
            target.next_check_at = datetime.now(timezone.utc)
        await session.commit()
    await message.answer(f"Monitoring for @{username} is {'enabled' if enabled else 'paused'}.")


@router.message(Command("pause"))
async def pause_target(message: Message) -> None:
    await _set_enabled(message, False)


@router.message(Command("resume"))
async def resume_target(message: Message) -> None:
    await _set_enabled(message, True)


@router.message(Command("interval"))
async def set_interval(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Usage: /interval @username seconds (minimum 10)")
        return
    try:
        username = validate_username(parts[1])
        interval = int(parts[2])
        if interval < 10 or interval > 86400:
            raise ValueError("Interval must be between 10 and 86400 seconds.")
    except ValueError as error:
        await message.answer(str(error))
        return
    async with SessionFactory() as session:
        target = await _get_target(session, username)
        if target is None:
            await message.answer(f"@{username} is not being monitored.")
            return
        target.interval_seconds = interval
        target.next_check_at = datetime.now(timezone.utc)
        await session.commit()
    await message.answer(f"Updated @{username}: checks will run every {interval} seconds.")


@router.message(Command("history"))
async def history(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) not in {2, 3}:
        await message.answer("Usage: /history @username [count]")
        return
    try:
        username = validate_username(parts[1])
        limit = min(20, max(1, int(parts[2]))) if len(parts) == 3 else 10
    except ValueError as error:
        await message.answer(f"Invalid argument: {error}")
        return

    async with SessionFactory() as session:
        target = await _get_target(session, username)
        if target is None:
            await message.answer(f"@{username} is not being monitored.")
            return
        rows = list(
            await session.scalars(
                select(CheckResult)
                .where(CheckResult.target_id == target.id)
                .order_by(desc(CheckResult.checked_at))
                .limit(limit)
            )
        )
    if not rows:
        await message.answer(f"No checks recorded for @{username} yet.")
        return
    lines = [f"Recent checks for @{username}:"]
    for row in rows:
        stamp = row.checked_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"• {stamp} — {row.status} — {row.method}")
    await message.answer("\n".join(lines))


@router.message(Command("settings"))
async def settings_command(message: Message, settings: Settings) -> None:
    proxy = settings.proxy_type or "disabled"
    await message.answer(
        "Current settings\n"
        f"Default interval: {settings.default_interval_seconds}s\n"
        f"Worker poll: {settings.check_poll_seconds}s\n"
        f"Concurrent checks: {settings.check_concurrency}\n"
        f"Shared proxy: {proxy}\n"
        f"Notifications: {'enabled' if settings.notification_enabled else 'disabled'}"
    )


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    async with SessionFactory() as session:
        total = await session.scalar(select(func.count(Target.id))) or 0
        active = await session.scalar(
            select(func.count(Target.id)).where(Target.enabled.is_(True))
        ) or 0
        heartbeat = await session.get(ServiceHeartbeat, "userbot")
    if heartbeat:
        age = (datetime.now(timezone.utc) - heartbeat.last_seen_at).total_seconds()
        worker_state = "online" if age < 45 else f"stale ({int(age)}s since heartbeat)"
    else:
        worker_state = "not seen yet"
    await message.answer(
        f"Bot: online\nUserbot worker: {worker_state}\n"
        f"Targets: {active} active / {total} total"
    )


@router.callback_query(F.data == "targets:list")
async def dashboard_targets(callback: CallbackQuery) -> None:
    await callback.answer()
    async with SessionFactory() as session:
        targets = list(await session.scalars(select(Target).order_by(Target.username.asc())))
    if not callback.message:
        return
    if not targets:
        await callback.message.answer("No targets yet. Use /add @username.")
        return
    lines = [
        f"• @{item.username} — {'active' if item.enabled else 'paused'} — "
        f"{item.last_status or 'pending'} — {item.interval_seconds}s"
        for item in targets
    ]
    await callback.message.answer("Monitored usernames:\n" + "\n".join(lines))


@router.callback_query(F.data == "targets:add")
async def dashboard_add(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer("Send /add @username [user|channel] to add a target.")


@router.callback_query(F.data == "settings:show")
async def dashboard_settings(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Default interval: {settings.default_interval_seconds}s\n"
            f"Shared proxy: {settings.proxy_type or 'disabled'}\n"
            "Use /interval @username seconds to change an individual target."
        )


@router.callback_query(F.data == "status:show")
async def dashboard_status(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer("Use /status for current bot and worker health.")
