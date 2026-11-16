from __future__ import annotations

from typing import Any

from pyrogram.errors import FloodWait
from pyrogram.raw.functions.contacts import Search

from monitor.domain import RateLimitedError, ResultStatus, SearchEvidence, TargetType


def _exact_match(response: Any, username: str, target_type: TargetType) -> str | None:
    expected = username.casefold()
    for user in getattr(response, "users", []) or []:
        candidate = getattr(user, "username", None)
        if candidate and candidate.casefold() == expected:
            if target_type in (TargetType.BOTH, TargetType.USER):
                return "A secondary Telegram search returned the exact user username."
    for chat in getattr(response, "chats", []) or []:
        candidate = getattr(chat, "username", None)
        if candidate and candidate.casefold() == expected:
            if target_type in (TargetType.BOTH, TargetType.CHANNEL):
                return "A secondary Telegram search returned the exact channel/supergroup username."
    return None


async def search_username(client: Any, username: str, target_type: TargetType) -> SearchEvidence:
    method = "contacts.search"
    try:
        response = await client.invoke(Search(q=username, limit=20))
        details = _exact_match(response, username, target_type)
        if details:
            return SearchEvidence(ResultStatus.OCCUPIED, method, details)
        return SearchEvidence(
            ResultStatus.INCONCLUSIVE,
            method,
            "Secondary search returned no exact username match.",
        )
    except FloodWait as error:
        seconds = getattr(error, "value", None) or getattr(error, "x", None) or 1
        raise RateLimitedError(seconds) from error
    except Exception as error:
        return SearchEvidence(
            ResultStatus.INCONCLUSIVE,
            method,
            f"Secondary search failed: {getattr(error, 'ID', type(error).__name__)}.",
        )
