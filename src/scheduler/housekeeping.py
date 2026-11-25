"""Periodic housekeeping scheduler for data retention and temporary file cleanup."""

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.storage.database import Database
from src.storage.media_governance import cleanup_temp_files

logger = logging.getLogger(__name__)


def build_housekeeping_scheduler(
    *,
    database: Database,
    timezone_name: str,
    retention_days: int,
) -> AsyncIOScheduler:
    """Configure an AsyncIOScheduler running periodic data hygiene jobs."""
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(timezone_name))

    async def run_housekeeping() -> None:
        removed_files = cleanup_temp_files(max_age_minutes=15)
        deleted_rows = await database.purge_expired_data(retention_days=retention_days)
        logger.info(
            "Housekeeping completed (removed_temp_files=%d, purged_db=%s)",
            removed_files,
            deleted_rows,
        )

    scheduler.add_job(run_housekeeping, trigger="interval", hours=12, id="housekeeping")
    return scheduler
