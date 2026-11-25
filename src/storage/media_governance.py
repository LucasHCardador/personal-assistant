"""Ephemeral media governance and temporary file sanitization utilities."""

import io
import logging
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

TEMP_MEDIA_PREFIX = "pa_ephemeral_"


@contextmanager
def ephemeral_memory_buffer() -> Iterator[io.BytesIO]:
    """Yield an in-memory BytesIO buffer and guarantee immediate disposal on exit."""
    buffer = io.BytesIO()
    try:
        yield buffer
    finally:
        buffer.seek(0)
        buffer.truncate(0)
        buffer.close()


def cleanup_temp_files(max_age_minutes: int = 15) -> int:
    """Remove any stray temporary media files older than `max_age_minutes`."""
    temp_dir = Path(tempfile.gettempdir())
    cutoff_ts = time.time() - (max_age_minutes * 60)
    removed = 0

    for item in temp_dir.glob(f"{TEMP_MEDIA_PREFIX}*"):
        try:
            if item.is_file() and item.stat().st_mtime < cutoff_ts:
                item.unlink(missing_ok=True)
                removed += 1
        except OSError as exc:
            logger.warning("Failed to remove temporary file %s: %s", item.name, exc)

    return removed
