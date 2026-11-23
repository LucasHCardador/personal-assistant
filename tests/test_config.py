"""Unit tests for environment-driven application configuration."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings parses required and comma-separated values from env."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-telegram-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "111222333, 444555666")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini-key")
    monkeypatch.setenv("MORNING_SUMMARY_TIME", "7:30")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.telegram_bot_token == "dummy-telegram-token"
    assert settings.telegram_allowed_user_ids == [111222333, 444555666]
    assert settings.gemini_api_key == "dummy-gemini-key"
    assert settings.morning_summary_time == "07:30"


def test_settings_rejects_invalid_morning_summary_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify invalid 24h time strings fail validation."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-telegram-token")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini-key")
    monkeypatch.setenv("MORNING_SUMMARY_TIME", "25:99")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
