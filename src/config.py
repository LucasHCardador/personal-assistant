"""Application configuration loaded strictly from environment variables."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, environment-driven application settings.

    All sensitive values and user-specific preferences must be provided via
    environment variables or a local `.env` file (never hardcoded).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(..., min_length=1)
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # LLM Provider
    llm_provider: Literal["gemini", "anthropic", "openai_compatible"] = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    llm_fallback_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gemini-3.1-flash-lite"]
    )
    llm_base_url: str | None = None

    # Speech-to-Text (fallback for providers without native audio input)
    stt_provider: Literal["auto", "groq", "openai", "none"] = "auto"
    stt_api_key: str = ""

    # Google Ecosystem (OAuth 2.0)
    google_credentials_path: Path = Path("/app/credentials/credentials.json")
    google_token_path: Path = Path("/app/credentials/token.json")
    google_sheets_car_id: str | None = None
    google_sheets_budget_id: str | None = None

    # Scheduler & Localization
    timezone: str = "America/Sao_Paulo"
    morning_summary_time: str = "07:30"
    weekly_summary_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] = "sun"
    weekly_summary_time: str = "19:00"

    # Text-to-Speech (TTS)
    tts_enabled: bool = True
    tts_voice: str = "pt-BR-AntonioNeural"

    # Storage, Governance & Logging
    database_path: Path = Path("/app/data/assistant.db")
    data_retention_days: int = Field(default=30, ge=1, le=3650)
    log_level: str = "INFO"

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, value: object) -> list[int]:
        """Parse comma-separated Telegram user IDs or an integer list."""
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [int(item) for item in value]
        raise ValueError("TELEGRAM_ALLOWED_USER_IDS must be a comma-separated list of integers.")

    @field_validator("llm_fallback_models", mode="before")
    @classmethod
    def parse_fallback_models(cls, value: object) -> list[str]:
        """Parse comma-separated fallback model names or a string list."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("LLM_FALLBACK_MODELS must be a comma-separated list of model names.")

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        """Normalize empty string URLs to None."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("morning_summary_time", "weekly_summary_time")
    @classmethod
    def validate_summary_time(cls, value: str) -> str:
        """Ensure summary time settings follow 24h HH:MM format."""
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Summary time must follow HH:MM format.")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Summary time must represent a valid 24h time.")
        return f"{hour:02d}:{minute:02d}"


def get_settings() -> Settings:
    """Load and validate application settings from the environment."""
    return Settings()  # type: ignore[call-arg]
