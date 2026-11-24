"""Telegram Application builder registering commands, callbacks, and multimodal handlers."""

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from src.agent.orchestrator import AgentOrchestrator
from src.agent.tools.executor import ToolExecutor
from src.bot.handlers import BotHandlers
from src.config import Settings
from src.storage.database import Database


def build_telegram_application(
    *,
    settings: Settings,
    orchestrator: AgentOrchestrator,
    database: Database,
    tool_executor: ToolExecutor | None = None,
) -> Application:
    """Create and configure the python-telegram-bot Application."""
    app = Application.builder().token(settings.telegram_bot_token).concurrent_updates(True).build()

    handlers = BotHandlers(
        allowed_user_ids=settings.telegram_allowed_user_ids,
        orchestrator=orchestrator,
        database=database,
        tool_executor=tool_executor,
    )

    app.add_handler(CommandHandler("start", handlers.start_command))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("clear", handlers.clear_command))
    app.add_handler(CallbackQueryHandler(handlers.undo_callback, pattern=r"^undo:\d+$"))
    app.add_handler(
        CallbackQueryHandler(handlers.confirmation_callback, pattern=r"^(confirm|cancel):\d+$")
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handlers.voice_message))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.photo_message))

    return app
