"""Google Gemini provider with native multimodal (text, image, audio) & JSON schema support."""

import logging

from google import genai
from google.genai import errors, types

from src.agent.providers.base import BaseLLMProvider
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
)

logger = logging.getLogger(__name__)
_TRANSIENT_STATUS_CODES = {429, 500, 503, 504}


class GeminiProvider(BaseLLMProvider):
    """Adapter for Google Gemini via the `google-genai` SDK."""

    supports_native_audio = True
    supports_vision = True

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_models: list[str] | None = None,
    ) -> None:
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30000),
        )
        candidates = [model, *(fallback_models or [])]
        self._models = list(dict.fromkeys(m for m in candidates if m))

    async def generate_structured_reply(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[MediaAttachment] | None = None,
    ) -> AssistantStructuredReply:
        """Call Gemini async API enforcing `AssistantStructuredReply` JSON schema."""
        contents: list[types.Content] = []
        for msg in history:
            role = "model" if msg.role == "assistant" else "user"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg.content)])
            )

        current_parts: list[types.Part] = [types.Part.from_text(text=user_text)]
        for attachment in attachments or []:
            current_parts.append(
                types.Part.from_bytes(data=attachment.data, mime_type=attachment.mime_type)
            )
        contents.append(types.Content(role="user", parts=current_parts))

        last_error: Exception | None = None
        for idx, model_name in enumerate(self._models):
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=AssistantStructuredReply,
                        temperature=0.2,
                    ),
                )
                if (
                    response.parsed is not None
                    and isinstance(response.parsed, AssistantStructuredReply)
                ):
                    return response.parsed
                if response.text:
                    return AssistantStructuredReply.model_validate_json(response.text)
                raise ValueError(f"Gemini model '{model_name}' returned an empty response.")
            except errors.APIError as exc:
                last_error = exc
                is_transient = exc.code in _TRANSIENT_STATUS_CODES
                has_fallback = idx < len(self._models) - 1
                if is_transient and has_fallback:
                    logger.warning(
                        "Gemini model '%s' returned %s; falling back to '%s'.",
                        model_name,
                        exc.code,
                        self._models[idx + 1],
                    )
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise ValueError("No Gemini models configured.")
