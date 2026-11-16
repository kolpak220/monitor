from __future__ import annotations

import logging
from typing import Any

from pyrogram.errors import FloodWait
from pyrogram.raw.functions.contacts import ResolveUsername

from monitor.domain import (
    RateLimitedError,
    ResultStatus,
    SearchEvidence,
    TargetType,
    classify_telegram_error,
)

logger = logging.getLogger(__name__)


def _matches_target(response: Any, target_type: TargetType) -> tuple[bool, str]:
    users = getattr(response, "users", []) or []
    chats = getattr(response, "chats", []) or []

    matched_user = any(getattr(user, "username", None) for user in users)
    matched_channel = any(getattr(chat, "username", None) for chat in chats)

    if target_type == TargetType.USER:
        return matched_user, "Telegram resolved a user account." if matched_user else ""
    if target_type == TargetType.CHANNEL:
        return matched_channel, "Telegram resolved a channel or supergroup." if matched_channel else ""
    if matched_user or matched_channel:
        kinds = []
        if matched_user:
            kinds.append("user account")
        if matched_channel:
            kinds.append("channel/supergroup")
        return True, "Telegram resolved: " + " and ".join(kinds) + "."
    return False, ""


async def resolve_username(client: Any, username: str, target_type: TargetType) -> SearchEvidence:
    method = "contacts.resolveUsername"
    try:
        response = await client.invoke(ResolveUsername(username=username))
        matched, details = _matches_target(response, target_type)
        if matched:
            return SearchEvidence(ResultStatus.OCCUPIED, method, details)
        return SearchEvidence(
            ResultStatus.INCONCLUSIVE,
            method,
            "Telegram returned no matching entity in the exact resolution response.",
        )
    except FloodWait as error:
        seconds = getattr(error, "value", None) or getattr(error, "x", None) or 1
        raise RateLimitedError(seconds) from error
    except Exception as error:
        status = classify_telegram_error(error)
        if status == ResultStatus.INCONCLUSIVE:
            logger.warning("Unclassified Telegram resolver error: %s", type(error).__name__)
            return SearchEvidence(
                status,
                method,
                f"Telegram resolver returned {getattr(error, 'ID', type(error).__name__)}.",
            )
        return SearchEvidence(
            status,
            method,
            f"Telegram resolver returned {getattr(error, 'ID', status.value)}.",
        )
