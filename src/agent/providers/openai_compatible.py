"""OpenAI-compatible provider (OpenAI, OpenRouter :free, Groq, Ollama, vLLM)."""

import base64
import json
from typing import Any

from openai import AsyncOpenAI

from src.agent.providers.base import BaseLLMProvider
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
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
    ) -> AssistantStructuredReply:
        """Call OpenAI-compatible API requesting strict JSON output."""
        schema_json = json.dumps(AssistantStructuredReply.model_json_schema(), ensure_ascii=False)
        json_system_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANTE: Responda EXCLUSIVAMENTE com um objeto JSON válido seguindo este schema:\n"
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

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content
        if not raw_content:
            raise ValueError("OpenAI-compatible provider returned an empty response.")
        return AssistantStructuredReply.model_validate_json(raw_content)
