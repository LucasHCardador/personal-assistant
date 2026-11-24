"""Abstract base interface for interchangeable LLM providers."""

from abc import ABC, abstractmethod

from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
)


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
    ) -> AssistantStructuredReply:
        """Generate a validated structured response from the underlying LLM."""
