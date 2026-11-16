import pytest

from monitor.domain import (
    ResultStatus,
    classify_telegram_error,
    normalize_username,
    validate_username,
)


class TelegramErrorStub(Exception):
    def __init__(self, identifier: str) -> None:
        self.ID = identifier
        super().__init__(identifier)


def test_normalize_username() -> None:
    assert normalize_username("  @Example_User  ") == "example_user"


@pytest.mark.parametrize(
    "value",
    ["@abcd", "ab", "bad-name", "1starts_with_digit", "name with space"],
)
def test_rejects_invalid_username(value: str) -> None:
    with pytest.raises(ValueError):
        validate_username(value)


def test_accepts_valid_username() -> None:
    assert validate_username("@Example_123") == "example_123"


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("USERNAME_PURCHASE_AVAILABLE", ResultStatus.COLLECTIBLE),
        ("USERNAME_NOT_OCCUPIED", ResultStatus.APPARENTLY_AVAILABLE),
        ("USERNAME_INVALID", ResultStatus.INVALID),
        ("USERNAME_OCCUPIED", ResultStatus.OCCUPIED),
        ("SOME_OTHER_ERROR", ResultStatus.INCONCLUSIVE),
    ],
)
def test_classifies_telegram_errors(identifier: str, expected: ResultStatus) -> None:
    assert classify_telegram_error(TelegramErrorStub(identifier)) == expected
