"""Abstract base interface for interchangeable LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
    ToolDefinition,
)

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
MAX_TOOL_ITERATIONS = 5


class BaseLLMProvider(ABC):
    """Unified contract for Gemini, Anthropic (Claude), and OpenAI-compatible models."""

    supports_native_audio: bool = False
    supports_vision: bool = True

    @abstractmethod
    async def generate_structured_reply(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[MediaAttachment] | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_executor: ToolCaller | None = None,
    ) -> AssistantStructuredReply:
        """Generate a validated structured response, optionally executing tool calls."""
