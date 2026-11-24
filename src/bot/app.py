"""Telegram Application builder registering commands and multimodal handlers."""

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from src.agent.orchestrator import AgentOrchestrator
from src.bot.handlers import BotHandlers
from src.config import Settings
from src.storage.database import Database


def build_telegram_application(
    *,
    settings: Settings,
    orchestrator: AgentOrchestrator,
    database: Database,
) -> Application:
    """Create and configure the python-telegram-bot Application."""
    app = Application.builder().token(settings.telegram_bot_token).build()

    handlers = BotHandlers(
        allowed_user_ids=settings.telegram_allowed_user_ids,
        orchestrator=orchestrator,
        database=database,
    )

    app.add_handler(CommandHandler("start", handlers.start_command))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("clear", handlers.clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handlers.voice_message))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.photo_message))

    return app
