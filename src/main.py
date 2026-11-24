"""Application entrypoint for the Personal Assistant service."""

import logging
import sys

from telegram.ext import Application

from src.agent.orchestrator import AgentOrchestrator
from src.agent.providers.factory import create_llm_provider
from src.agent.stt import create_audio_transcriber
from src.bot.app import build_telegram_application
from src.config import get_settings
from src.scheduler.housekeeping import build_housekeeping_scheduler
from src.storage.database import Database


def configure_logging(level: str) -> None:
    """Configure structured root logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


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
    orchestrator = AgentOrchestrator(
        provider=provider,
        database=database,
        timezone_name=settings.timezone,
        transcriber=transcriber,
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
    )

    async def on_startup(_: Application) -> None:
        await database.init()
        scheduler.start()
        logger.info("Database initialized and housekeeping scheduler started.")

    async def on_shutdown(_: Application) -> None:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("Personal Assistant shutdown complete.")

    app.post_init = on_startup
    app.post_shutdown = on_shutdown
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
