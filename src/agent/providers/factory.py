"""Factory to instantiate the configured LLM provider from Settings."""

from src.agent.providers.anthropic_provider import AnthropicProvider
from src.agent.providers.base import BaseLLMProvider
from src.agent.providers.gemini import GeminiProvider
from src.agent.providers.openai_compatible import OpenAICompatibleProvider
from src.config import Settings


def create_llm_provider(settings: Settings) -> BaseLLMProvider:
    """Instantiate the active LLM provider based on `settings.llm_provider`."""
    if settings.llm_provider == "gemini":
        if not settings.llm_api_key:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=gemini.")
        return GeminiProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            fallback_models=settings.llm_fallback_models,
        )

    if settings.llm_provider == "anthropic":
        if not settings.llm_api_key:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=anthropic.")
        return AnthropicProvider(api_key=settings.llm_api_key, model=settings.llm_model)

    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
