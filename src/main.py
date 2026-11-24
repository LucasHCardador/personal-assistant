"""Application entrypoint for the Personal Assistant service."""

import logging
import sys

import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telegram.ext import Application

from src.agent.orchestrator import AgentOrchestrator
from src.agent.providers.factory import create_llm_provider
from src.agent.stt import create_audio_transcriber
from src.agent.tools import ToolExecutor, ToolRegistry
from src.agent.tts import SpeechSynthesizer
from src.bot.app import build_telegram_application
from src.config import Settings, get_settings
from src.integrations.google_auth import load_google_credentials
from src.integrations.google_calendar import GoogleCalendarService
from src.integrations.google_sheets import GoogleSheetsService
from src.scheduler.housekeeping import build_housekeeping_scheduler
from src.scheduler.proactive import ProactiveNotifier, register_proactive_jobs
from src.storage.database import Database


def configure_logging(level: str) -> None:
    """Configure structured root logging and silence noisy HTTP client loggers."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Prevent httpx from logging full Telegram Bot API URLs (which contain the bot token)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _load_google_credentials_if_available(
    settings: Settings, logger: logging.Logger
) -> Credentials | None:
    """Load Google OAuth credentials if `token.json` exists and is valid."""
    if not settings.google_token_path.exists():
        logger.warning(
            "Google OAuth token not found at '%s'; Google integrations will be disabled. "
            "Run 'python -m scripts.auth_google' to authorize.",
            settings.google_token_path,
        )
        return None

    try:
        return load_google_credentials(
            settings.google_credentials_path,
            settings.google_token_path,
        )
    except Exception as exc:
        logger.warning(
            "Failed to load Google OAuth credentials (%s); "
            "Google integrations will be disabled.",
            exc,
        )
        return None


def _build_sheets_service(
    settings: Settings,
    creds: Credentials | None,
    logger: logging.Logger,
) -> GoogleSheetsService | None:
    """Initialize GoogleSheetsService if credentials and spreadsheet IDs are configured."""
    if creds is None:
        return None

    if not settings.google_sheets_car_id and not settings.google_sheets_budget_id:
        logger.warning(
            "GOOGLE_SHEETS_CAR_ID and GOOGLE_SHEETS_BUDGET_ID are not configured; "
            "Google Sheets tools will be disabled."
        )
        return None

    try:
        client = gspread.authorize(creds)
        return GoogleSheetsService(
            client=client,
            car_spreadsheet_id=settings.google_sheets_car_id,
            budget_spreadsheet_id=settings.google_sheets_budget_id,
            timezone_name=settings.timezone,
        )
    except Exception as exc:
        logger.warning(
            "Failed to initialize Google Sheets integration (%s); "
            "Google Sheets tools will be disabled.",
            exc,
        )
        return None


def _build_calendar_service(
    settings: Settings,
    creds: Credentials | None,
    logger: logging.Logger,
) -> GoogleCalendarService | None:
    """Initialize GoogleCalendarService if OAuth credentials are available."""
    if creds is None:
        return None

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return GoogleCalendarService(
            service=service,
            timezone_name=settings.timezone,
        )
    except Exception as exc:
        logger.warning(
            "Failed to initialize Google Calendar integration (%s); "
            "Google Calendar tools will be disabled.",
            exc,
        )
        return None


def main() -> None:
    """Initialize configuration, services, scheduler, and start Telegram polling."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting Personal Assistant "
        "(provider=%s, model=%s, timezone=%s, allowed_users=%d, retention_days=%d)",
        settings.llm_provider,
        settings.llm_model,
        settings.timezone,
        len(settings.telegram_allowed_user_ids),
        settings.data_retention_days,
    )

    database = Database(settings.database_path)
    provider = create_llm_provider(settings)
    transcriber = create_audio_transcriber(settings)
    tts = SpeechSynthesizer(voice=settings.tts_voice) if settings.tts_enabled else None

    google_creds = _load_google_credentials_if_available(settings, logger)
    sheets_service = _build_sheets_service(settings, google_creds, logger)
    calendar_service = _build_calendar_service(settings, google_creds, logger)
    tool_registry = ToolRegistry(
        enable_car_tools=bool(sheets_service and sheets_service.has_car_sheet),
        enable_budget_tools=bool(sheets_service and sheets_service.has_budget_sheet),
        enable_calendar_tools=calendar_service is not None,
        enable_undo_tool=bool(sheets_service or calendar_service),
    )
    tool_executor = ToolExecutor(
        database=database,
        sheets_service=sheets_service,
        calendar_service=calendar_service,
        timezone_name=settings.timezone,
    )

    orchestrator = AgentOrchestrator(
        provider=provider,
        database=database,
        timezone_name=settings.timezone,
        transcriber=transcriber,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
    )
    scheduler = build_housekeeping_scheduler(
        database=database,
        timezone_name=settings.timezone,
        retention_days=settings.data_retention_days,
    )

    app = build_telegram_application(
        settings=settings,
        orchestrator=orchestrator,
        database=database,
        tool_executor=tool_executor,
        tts=tts,
    )

    async def on_startup(application: Application) -> None:
        await database.init()
        notifier = ProactiveNotifier(
            bot=application.bot,
            database=database,
            settings=settings,
            calendar_service=calendar_service,
            sheets_service=sheets_service,
            tts=tts,
        )
        register_proactive_jobs(scheduler, notifier, settings)
        scheduler.start()
        logger.info(
            "Database initialized and scheduler started with proactive jobs (tools_enabled=%d).",
            len(tool_registry.definitions),
        )

    async def on_shutdown(_: Application) -> None:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("Personal Assistant shutdown complete.")

    app.post_init = on_startup
    app.post_shutdown = on_shutdown
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
