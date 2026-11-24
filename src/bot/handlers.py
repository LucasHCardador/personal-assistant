"""Telegram bot command and multimodal message handlers."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from src.agent.orchestrator import AgentOrchestrator
from src.agent.schemas import AssistantStructuredReply, MediaAttachment
from src.agent.tools.executor import ToolExecutor
from src.bot.formatters import (
    format_help_message,
    format_structured_reply,
    format_welcome_message,
)
from src.bot.middleware import ensure_authorized
from src.storage.database import Database
from src.storage.media_governance import ephemeral_memory_buffer

logger = logging.getLogger(__name__)


class BotHandlers:
    """Encapsulates Telegram update handlers with whitelist and ephemeral media handling."""

    def __init__(
        self,
        *,
        allowed_user_ids: list[int],
        orchestrator: AgentOrchestrator,
        database: Database,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._allowed_user_ids = allowed_user_ids
        self._orchestrator = orchestrator
        self._db = database
        self._tool_executor = tool_executor

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return
        if update.effective_message:
            await update.effective_message.reply_text(
                format_welcome_message(), parse_mode=ParseMode.HTML
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return
        if update.effective_message:
            await update.effective_message.reply_text(
                format_help_message(), parse_mode=ParseMode.HTML
            )

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear short-term conversation memory for the current user."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return
        user = update.effective_user
        if user and update.effective_message:
            deleted = await self._db.clear_chat_history(user.id)
            reply = AssistantStructuredReply(
                intent="action_result",
                summary="Histórico recente da conversa limpo.",
                details=[f"Mensagens removidas: {deleted}"],
            )
            await update.effective_message.reply_text(
                format_structured_reply(reply), parse_mode=ParseMode.HTML
            )

    async def text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle free-form text messages."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return
        message = update.effective_message
        user = update.effective_user
        if not message or not user or not message.text:
            return

        await message.chat.send_action(ChatAction.TYPING)
        await self._reply_from_agent(update=update, user_id=user.id, text=message.text)

    async def voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice/audio messages strictly in memory (zero disk persistence)."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return
        message = update.effective_message
        user = update.effective_user
        if not message or not user:
            return

        media = message.voice or message.audio
        if not media:
            return

        await message.chat.send_action(ChatAction.TYPING)
        tg_file = await context.bot.get_file(media.file_id)
        mime_type = getattr(media, "mime_type", None) or "audio/ogg"

        with ephemeral_memory_buffer() as buffer:
            await tg_file.download_to_memory(out=buffer)
            attachment = MediaAttachment(
                kind="audio",
                mime_type=mime_type,
                data=buffer.getvalue(),
            )
            await self._reply_from_agent(
                update=update,
                user_id=user.id,
                text=message.caption,
                attachments=[attachment],
            )

    async def photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle photo messages strictly in memory (zero disk persistence)."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return
        message = update.effective_message
        user = update.effective_user
        if not message or not user or not message.photo:
            return

        await message.chat.send_action(ChatAction.TYPING)
        largest_photo = message.photo[-1]
        tg_file = await context.bot.get_file(largest_photo.file_id)

        with ephemeral_memory_buffer() as buffer:
            await tg_file.download_to_memory(out=buffer)
            attachment = MediaAttachment(
                kind="image",
                mime_type="image/jpeg",
                data=buffer.getvalue(),
            )
            await self._reply_from_agent(
                update=update,
                user_id=user.id,
                text=message.caption,
                attachments=[attachment],
            )

    async def _reply_from_agent(
        self,
        *,
        update: Update,
        user_id: int,
        text: str | None = None,
        attachments: list[MediaAttachment] | None = None,
    ) -> None:
        """Invoke the agent orchestrator and render a deterministic response."""
        message = update.effective_message
        if not message:
            return

        try:
            reply = await self._orchestrator.process_message(
                user_id=user_id,
                text=text,
                attachments=attachments,
            )
        except Exception as exc:
            logger.exception("Error processing message for user_id=%s: %s", user_id, exc)
            reply = AssistantStructuredReply(
                intent="error",
                summary="Não consegui processar sua solicitação agora.",
                next_step_hint="Tente novamente em alguns instantes.",
            )

        reply_markup: InlineKeyboardMarkup | None = None
        if reply.undo_action_id is not None:
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Desfazer",
                            callback_data=f"undo:{reply.undo_action_id}",
                        )
                    ]
                ]
            )

        await message.reply_text(
            format_structured_reply(reply),
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )

    async def undo_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline 'Desfazer' button clicks for recorded sheet writes."""
        if not await ensure_authorized(update, self._allowed_user_ids):
            return

        query = update.callback_query
        user = update.effective_user
        if not query or not user or not query.data:
            return

        await query.answer()

        if self._tool_executor is None:
            reply = AssistantStructuredReply(
                intent="error",
                summary="O recurso de desfazer não está disponível no momento.",
            )
            if query.message:
                await query.message.reply_text(
                    format_structured_reply(reply), parse_mode=ParseMode.HTML
                )
            return

        try:
            action_id = int(query.data.split(":", 1)[1])
        except (IndexError, ValueError):
            return

        result = await self._tool_executor.undo_action(user_id=user.id, action_id=action_id)
        if result.get("status") == "ok":
            await query.edit_message_reply_markup(reply_markup=None)
            reply = AssistantStructuredReply(
                intent="action_result",
                summary="Lançamento desfeito com sucesso.",
                details=[
                    f"Aba: {result.get('worksheet', '-')}",
                    f"ID removido: {result.get('record_id', '-')}",
                ],
            )
        elif result.get("status") == "not_found":
            await query.edit_message_reply_markup(reply_markup=None)
            reply = AssistantStructuredReply(
                intent="clarification",
                summary="Esta ação já foi desfeita ou não está mais disponível.",
            )
        else:
            reply = AssistantStructuredReply(
                intent="error",
                summary="Não foi possível desfazer este lançamento.",
                details=[str(result.get("error", "Erro desconhecido"))],
            )

        if query.message:
            await query.message.reply_text(
                format_structured_reply(reply), parse_mode=ParseMode.HTML
            )
