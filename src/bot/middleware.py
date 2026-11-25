"""Telegram authorization middleware based on TELEGRAM_ALLOWED_USER_IDS."""

import logging

from telegram import Update

logger = logging.getLogger(__name__)


def is_authorized_user(user_id: int | None, allowed_user_ids: list[int]) -> bool:
    """Return True only when user_id is present and explicitly listed in allowed_user_ids."""
    if user_id is None or not allowed_user_ids:
        return False
    return user_id in allowed_user_ids


async def ensure_authorized(update: Update, allowed_user_ids: list[int]) -> bool:
    """Reject unauthorized Telegram updates cleanly without leaking internal state."""
    user = update.effective_user
    user_id = user.id if user else None

    if is_authorized_user(user_id, allowed_user_ids):
        return True

    logger.warning("Unauthorized access attempt from Telegram user_id=%s", user_id)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Acesso não autorizado. Adicione seu user_id em TELEGRAM_ALLOWED_USER_IDS."
        )
    return False
