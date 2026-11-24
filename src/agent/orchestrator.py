"""Agent orchestrator handling multimodal normalization, memory, tools, and structured replies."""

import logging
from typing import Any

from src.agent.providers.base import BaseLLMProvider
from src.agent.schemas import AssistantStructuredReply, MediaAttachment
from src.agent.stt import AudioTranscriber
from src.agent.system_prompt import build_system_prompt
from src.agent.tools.executor import ToolExecutor
from src.agent.tools.registry import ToolRegistry
from src.storage.database import Database

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates LLM provider calls, tool execution, STT fallback, and memory."""

    def __init__(
        self,
        *,
        provider: BaseLLMProvider,
        database: Database,
        timezone_name: str,
        transcriber: AudioTranscriber | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        history_limit: int = 10,
    ) -> None:
        self._provider = provider
        self._db = database
        self._timezone_name = timezone_name
        self._transcriber = transcriber
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._history_limit = history_limit

    async def process_message(
        self,
        *,
        user_id: int,
        text: str | None = None,
        attachments: list[MediaAttachment] | None = None,
    ) -> AssistantStructuredReply:
        """Process a user message (text, audio, or image) and return a structured reply."""
        prompt_parts: list[str] = [text.strip()] if text and text.strip() else []
        forward_attachments: list[MediaAttachment] = []

        for attachment in attachments or []:
            if attachment.kind == "audio" and not self._provider.supports_native_audio:
                if self._transcriber is None:
                    return AssistantStructuredReply(
                        intent="clarification",
                        summary=(
                            "O provedor de IA configurado não processa áudio nativamente e "
                            "nenhum serviço de transcrição (STT_PROVIDER) está ativo."
                        ),
                        next_step_hint=(
                            "Envie sua mensagem em texto ou configure STT_PROVIDER no .env."
                        ),
                    )
                transcript = await self._transcriber.transcribe(
                    attachment.data, mime_type=attachment.mime_type
                )
                if transcript:
                    prompt_parts.append(f"[Áudio transcrito]: {transcript}")
            else:
                forward_attachments.append(attachment)

        effective_text = "\n".join(prompt_parts).strip()
        if not effective_text and forward_attachments:
            effective_text = "Analise a mídia enviada e ajude o usuário conforme o contexto."

        if not effective_text:
            return AssistantStructuredReply(
                intent="clarification",
                summary="Não recebi texto ou mídia válida para processar.",
            )

        history = await self._db.get_recent_messages(user_id=user_id, limit=self._history_limit)
        tools = (
            self._tool_registry.definitions
            if self._tool_registry and self._tool_registry.has_tools
            else None
        )
        system_prompt = build_system_prompt(self._timezone_name, has_tools=bool(tools))

        last_action_id: int | None = None

        if tools and self._tool_executor is not None:
            executor = self._tool_executor

            async def _call_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
                nonlocal last_action_id
                result = await executor.execute(
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=args,
                )
                if result.get("status") == "ok":
                    if tool_name == "undo_last_action":
                        last_action_id = None
                    elif "action_id" in result and result["action_id"] is not None:
                        last_action_id = int(result["action_id"])
                return result

            reply = await self._provider.generate_structured_reply(
                system_prompt=system_prompt,
                history=history,
                user_text=effective_text,
                attachments=forward_attachments or None,
                tools=tools,
                tool_executor=_call_tool,
            )
        else:
            reply = await self._provider.generate_structured_reply(
                system_prompt=system_prompt,
                history=history,
                user_text=effective_text,
                attachments=forward_attachments or None,
            )

        reply.set_undo_action_id(last_action_id)

        # Persist only text turns (ephemeral media bytes are never stored)
        user_record = effective_text
        if forward_attachments and reply.media_summary:
            user_record = f"{effective_text}\n[Resumo da mídia]: {reply.media_summary}"

        assistant_record = reply.summary
        if reply.details:
            details_text = "; ".join(reply.details)
            assistant_record = f"{reply.summary} ({details_text})"

        await self._db.add_chat_message(user_id=user_id, role="user", content=user_record)
        await self._db.add_chat_message(
            user_id=user_id, role="assistant", content=assistant_record
        )

        logger.info("Processed message for user_id=%s (intent=%s)", user_id, reply.intent)
        return reply
