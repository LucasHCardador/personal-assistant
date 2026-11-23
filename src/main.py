"""Application entrypoint for the Personal Assistant service."""

import logging
import sys

from src.config import get_settings


def configure_logging(level: str) -> None:
    """Configure structured root logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def main() -> None:
    """Initialize configuration, logging, and start the assistant runtime."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = logging.getLogger(__name__)
    logger.info(
        "Personal Assistant initialized (model=%s, timezone=%s, allowed_users=%d)",
        settings.gemini_model,
        settings.timezone,
        len(settings.telegram_allowed_user_ids),
    )


if __name__ == "__main__":
    main()
