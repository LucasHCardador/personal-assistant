"""Unit tests for Telegram whitelist authorization middleware."""

from src.bot.middleware import is_authorized_user


def test_authorized_user_allowed() -> None:
    """Verify explicitly listed user IDs are authorized."""
    assert is_authorized_user(123456, [123456, 789012]) is True


def test_unlisted_user_denied() -> None:
    """Verify unknown user IDs are rejected."""
    assert is_authorized_user(999999, [123456, 789012]) is False


def test_empty_whitelist_or_none_user_denied() -> None:
    """Verify fail-closed behavior when whitelist is empty or user is None."""
    assert is_authorized_user(None, [123456]) is False
    assert is_authorized_user(123456, []) is False
