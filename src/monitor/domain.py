from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


class TargetType(StrEnum):
    BOTH = "both"
    USER = "user"
    CHANNEL = "channel"


class ResultStatus(StrEnum):
    OCCUPIED = "occupied"
    APPARENTLY_AVAILABLE = "apparently_available"
    COLLECTIBLE = "collectible"
    INVALID = "invalid"
    INCONCLUSIVE = "inconclusive"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


@dataclass(slots=True)
class SearchEvidence:
    status: ResultStatus
    method: str
    details: str


class RateLimitedError(Exception):
    def __init__(self, seconds: int) -> None:
        self.seconds = max(1, int(seconds))
        super().__init__(f"Telegram requested a retry after {self.seconds} seconds")


def normalize_username(value: str) -> str:
    username = value.strip()
    if username.startswith("@"):
        username = username[1:]
    return username.lower()


def validate_username(value: str) -> str:
    username = normalize_username(value)
    if not USERNAME_RE.fullmatch(username):
        raise ValueError(
            "Username must be 5–32 characters, start with a letter, "
            "and contain only letters, digits or underscores."
        )
    return username


def classify_telegram_error(error: Exception) -> ResultStatus:
    identifier = str(getattr(error, "ID", "")).upper()
    message = str(error).upper()
    token = identifier or message

    if "USERNAME_PURCHASE_AVAILABLE" in token:
        return ResultStatus.COLLECTIBLE
    if "USERNAME_NOT_OCCUPIED" in token:
        return ResultStatus.APPARENTLY_AVAILABLE
    if "USERNAME_INVALID" in token:
        return ResultStatus.INVALID
    if "USERNAME_OCCUPIED" in token:
        return ResultStatus.OCCUPIED
    return ResultStatus.INCONCLUSIVE
