"""Google Gemini provider with native multimodal (text, image, audio) & tool-calling support."""

import asyncio
import logging
import random

from google import genai
from google.genai import errors, types

from src.agent.providers.base import (
    MAX_TOOL_ITERATIONS,
    BaseLLMProvider,
    ToolCaller,
    TransientLLMError,
)
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
    ToolDefinition,
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

    async def _generate_with_fallback(
        self,
        *,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse:
        """Call Gemini async API with fallback models and backoff on transient errors."""
        last_error: Exception | None = None
        max_rounds = 4

        for round_idx in range(max_rounds):
            for idx, model_name in enumerate(self._models):
                try:
                    return await self._client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                except errors.APIError as exc:
                    last_error = exc
                    if exc.code not in _TRANSIENT_STATUS_CODES:
                        raise

                    has_next_model = idx < len(self._models) - 1
                    if has_next_model:
                        logger.warning(
                            "Gemini model '%s' returned %s; falling back to '%s'.",
                            model_name,
                            exc.code,
                            self._models[idx + 1],
                        )
                        continue

            if round_idx < max_rounds - 1:
                delay = 2.0 * (2**round_idx) + random.uniform(0.0, 0.8)
                logger.warning(
                    "All Gemini models returned transient errors (round %d/%d); retrying in %.1fs.",
                    round_idx + 1,
                    max_rounds,
                    delay,
                )
                await asyncio.sleep(delay)

        raise TransientLLMError(
            f"All Gemini models failed with transient error: {last_error}"
        ) from last_error

    @staticmethod
    def _parse_structured_response(
        response: types.GenerateContentResponse,
    ) -> AssistantStructuredReply:
        if (
            response.parsed is not None
            and isinstance(response.parsed, AssistantStructuredReply)
        ):
            return response.parsed
        if response.text:
            return AssistantStructuredReply.model_validate_json(response.text)
        raise ValueError("Gemini model returned an empty response.")

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
        """Call Gemini async API with optional tool-calling loop before structured reply."""
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

        gemini_tools: list[types.Tool] | None = None
        if tools and tool_executor is not None:
            declarations = [
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters_json_schema=t.parameters_schema,
                )
                for t in tools
            ]
            gemini_tools = [types.Tool(function_declarations=declarations)]

        if gemini_tools and tool_executor is not None:
            for _ in range(MAX_TOOL_ITERATIONS):
                # Do not set response_mime_type/response_schema while tools are active,
                # otherwise Gemini skips function_calls and emits raw JSON directly.
                response = await self._generate_with_fallback(
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=gemini_tools,
                        temperature=0.2,
                    ),
                )
                function_calls = response.function_calls or []
                if not function_calls:
                    if response.candidates and response.candidates[0].content:
                        contents.append(response.candidates[0].content)
                        contents.append(
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_text(
                                        text="Formate a resposta final exatamente no schema JSON."
                                    )
                                ],
                            )
                        )
                    break

                if response.candidates and response.candidates[0].content:
                    contents.append(response.candidates[0].content)

                response_parts: list[types.Part] = []
                for fc in function_calls:
                    tool_name = fc.name or ""
                    args = dict(fc.args or {})
                    result = await tool_executor(tool_name, args)
                    response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response=result,
                        )
                    )
                contents.append(types.Content(role="user", parts=response_parts))

        final_response = await self._generate_with_fallback(
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=AssistantStructuredReply,
                temperature=0.2,
            ),
        )
        return self._parse_structured_response(final_response)
