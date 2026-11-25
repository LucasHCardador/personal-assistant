"""OpenAI-compatible provider (OpenAI, OpenRouter :free, Groq, Ollama, vLLM)."""

import base64
import json
from typing import Any

from openai import AsyncOpenAI

from src.agent.providers.base import MAX_TOOL_ITERATIONS, BaseLLMProvider, ToolCaller
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
    ToolDefinition,
)


class OpenAICompatibleProvider(BaseLLMProvider):
    """Adapter for any OpenAI-compatible chat completions API."""

    supports_native_audio = False
    supports_vision = True

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)
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
        """Call OpenAI-compatible API with optional tool-calling loop and JSON output."""
        schema_json = json.dumps(AssistantStructuredReply.model_json_schema(), ensure_ascii=False)
        json_system_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANTE: Quando não estiver chamando uma ferramenta, responda EXCLUSIVAMENTE "
            "com um objeto JSON válido seguindo este schema:\n"
            f"{schema_json}"
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": json_system_prompt}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})

        image_attachments = [a for a in (attachments or []) if a.kind == "image"]
        if image_attachments:
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
            for attachment in image_attachments:
                encoded = base64.b64encode(attachment.data).decode("ascii")
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{attachment.mime_type};base64,{encoded}"},
                    }
                )
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": user_text})

        if tools and tool_executor is not None:
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_schema,
                    },
                }
                for t in tools
            ]
            for _ in range(MAX_TOOL_ITERATIONS):
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    tools=openai_tools,  # type: ignore[arg-type]
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                choice_msg = response.choices[0].message
                if not choice_msg.tool_calls:
                    if not choice_msg.content:
                        raise ValueError("OpenAI-compatible provider returned an empty response.")
                    return AssistantStructuredReply.model_validate_json(choice_msg.content)

                messages.append(choice_msg.model_dump(exclude_none=True))
                for tc in choice_msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    result = await tool_executor(tc.function.name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )

        final_response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw_content = final_response.choices[0].message.content
        if not raw_content:
            raise ValueError("OpenAI-compatible provider returned an empty response.")
        return AssistantStructuredReply.model_validate_json(raw_content)
