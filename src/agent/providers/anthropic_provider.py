"""Anthropic (Claude) provider using tool-use for domain tools and structured outputs."""

import base64
import json
from typing import Any

from anthropic import AsyncAnthropic

from src.agent.providers.base import MAX_TOOL_ITERATIONS, BaseLLMProvider, ToolCaller
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
    ToolDefinition,
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
        tools: list[ToolDefinition] | None = None,
        tool_executor: ToolCaller | None = None,
    ) -> AssistantStructuredReply:
        """Call Claude with optional tool-calling loop before forced structured reply."""
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

        structured_tool = {
            "name": STRUCTURED_REPLY_TOOL_NAME,
            "description": "Return the final structured assistant response.",
            "input_schema": AssistantStructuredReply.model_json_schema(),
        }

        if tools and tool_executor is not None:
            domain_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters_schema,
                }
                for t in tools
            ]
            all_tools = [*domain_tools, structured_tool]

            for _ in range(MAX_TOOL_ITERATIONS):
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=1024,
                    temperature=0.2,
                    system=system_prompt,
                    messages=messages,  # type: ignore[arg-type]
                    tools=all_tools,  # type: ignore[arg-type]
                    tool_choice={"type": "any"},
                )

                tool_uses = [b for b in response.content if b.type == "tool_use"]
                if not tool_uses:
                    break

                for block in tool_uses:
                    if block.name == STRUCTURED_REPLY_TOOL_NAME:
                        return AssistantStructuredReply.model_validate(block.input)

                messages.append({"role": "assistant", "content": response.content})
                tool_results: list[dict[str, Any]] = []
                for block in tool_uses:
                    result = await tool_executor(block.name, dict(block.input or {}))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                messages.append({"role": "user", "content": tool_results})

        final_response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0.2,
            system=system_prompt,
            messages=messages,  # type: ignore[arg-type]
            tools=[structured_tool],  # type: ignore[arg-type]
            tool_choice={"type": "tool", "name": STRUCTURED_REPLY_TOOL_NAME},
        )

        for block in final_response.content:
            if block.type == "tool_use" and block.name == STRUCTURED_REPLY_TOOL_NAME:
                return AssistantStructuredReply.model_validate(block.input)

        raise ValueError("Anthropic did not return the structured reply tool payload.")
