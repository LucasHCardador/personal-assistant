"""Anthropic (Claude) provider using forced tool-use for strict structured outputs."""

import base64
from typing import Any

from anthropic import AsyncAnthropic

from src.agent.providers.base import BaseLLMProvider
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
)

STRUCTURED_REPLY_TOOL_NAME = "format_assistant_reply"


class AnthropicProvider(BaseLLMProvider):
    """Adapter for Claude models via the official `anthropic` SDK."""

    supports_native_audio = False
    supports_vision = True

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate_structured_reply(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[MediaAttachment] | None = None,
    ) -> AssistantStructuredReply:
        """Call Claude forcing a structured JSON output via tool_choice."""
        messages: list[dict[str, Any]] = [
            {"role": msg.role, "content": msg.content} for msg in history
        ]

        user_blocks: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for attachment in attachments or []:
            if attachment.kind == "image":
                encoded = base64.b64encode(attachment.data).decode("ascii")
                user_blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": attachment.mime_type,
                            "data": encoded,
                        },
                    }
                )
        messages.append({"role": "user", "content": user_blocks})

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0.2,
            system=system_prompt,
            messages=messages,
            tools=[
                {
                    "name": STRUCTURED_REPLY_TOOL_NAME,
                    "description": "Return the final structured assistant response.",
                    "input_schema": AssistantStructuredReply.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": STRUCTURED_REPLY_TOOL_NAME},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == STRUCTURED_REPLY_TOOL_NAME:
                return AssistantStructuredReply.model_validate(block.input)

        raise ValueError("Anthropic did not return the structured reply tool payload.")
