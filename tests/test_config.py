"""Unit tests for environment-driven application configuration."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Settings parses required, provider, and comma-separated values from env."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-telegram-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "111222333, 444555666")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "dummy-llm-key")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-5")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("MORNING_SUMMARY_TIME", "7:30")
    monkeypatch.setenv("DATA_RETENTION_DAYS", "15")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.telegram_bot_token == "dummy-telegram-token"
    assert settings.telegram_allowed_user_ids == [111222333, 444555666]
    assert settings.llm_provider == "anthropic"
    assert settings.llm_api_key == "dummy-llm-key"
    assert settings.llm_model == "claude-sonnet-4-5"
    assert settings.llm_base_url is None
    assert settings.morning_summary_time == "07:30"
    assert settings.data_retention_days == 15


def test_settings_rejects_invalid_morning_summary_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify invalid 24h time strings fail validation."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-telegram-token")
    monkeypatch.setenv("MORNING_SUMMARY_TIME", "25:99")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_rejects_unsupported_llm_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify unsupported LLM providers fail validation."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-telegram-token")
    monkeypatch.setenv("LLM_PROVIDER", "unknown_provider")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
