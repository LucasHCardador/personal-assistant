"""Unit tests for multi-provider factory, orchestrator, and deterministic formatters."""

from pathlib import Path

import pytest

from src.agent.orchestrator import AgentOrchestrator
from src.agent.providers.anthropic_provider import AnthropicProvider
from src.agent.providers.base import BaseLLMProvider
from src.agent.providers.factory import create_llm_provider
from src.agent.providers.gemini import GeminiProvider
from src.agent.providers.openai_compatible import OpenAICompatibleProvider
from src.agent.schemas import AssistantStructuredReply, ChatMessage, MediaAttachment
from src.bot.formatters import format_structured_reply
from src.config import Settings
from src.storage.database import Database


class FakeProvider(BaseLLMProvider):
    """Test double for BaseLLMProvider."""

    def __init__(self, supports_native_audio: bool = False) -> None:
        self.supports_native_audio = supports_native_audio
        self.last_user_text: str | None = None

    async def generate_structured_reply(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        user_text: str,
        attachments: list[MediaAttachment] | None = None,
    ) -> AssistantStructuredReply:
        self.last_user_text = user_text
        return AssistantStructuredReply(
            intent="action_result",
            summary="Recebido com sucesso",
            details=["Item 1", "Valor <R$ 100>"],
            next_step_hint="Algo mais?",
            media_summary="Áudio sobre abastecimento de R$ 100",
        )


class FakeTranscriber:
    """Test double for AudioTranscriber."""

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        return "Abasteci duzentos reais"


def test_format_structured_reply_escapes_html() -> None:
    """Verify deterministic formatter escapes HTML entities safely."""
    reply = AssistantStructuredReply(
        intent="action_result",
        summary="Gasto <registrado>",
        details=["Mercado & Padaria"],
        next_step_hint="Confira na planilha",
    )
    rendered = format_structured_reply(reply)
    assert "✅ <b>Gasto &lt;registrado&gt;</b>" in rendered
    assert "• Mercado &amp; Padaria" in rendered
    assert "<i>Confira na planilha</i>" in rendered


def test_provider_factory_selects_expected_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify factory instantiates Gemini, Anthropic, and OpenAI-compatible adapters."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert isinstance(create_llm_provider(Settings(_env_file=None)), GeminiProvider)  # type: ignore[call-arg]

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert isinstance(create_llm_provider(Settings(_env_file=None)), AnthropicProvider)  # type: ignore[call-arg]

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    assert isinstance(
        create_llm_provider(Settings(_env_file=None)),  # type: ignore[call-arg]
        OpenAICompatibleProvider,
    )


async def test_orchestrator_audio_fallback_without_transcriber(tmp_path: Path) -> None:
    """Verify non-audio LLM without STT returns a clear clarification reply."""
    db = Database(tmp_path / "orch.db")
    await db.init()

    orchestrator = AgentOrchestrator(
        provider=FakeProvider(supports_native_audio=False),
        database=db,
        timezone_name="America/Sao_Paulo",
        transcriber=None,
    )

    reply = await orchestrator.process_message(
        user_id=123,
        attachments=[MediaAttachment(kind="audio", mime_type="audio/ogg", data=b"ogg")],
    )
    assert reply.intent == "clarification"
    assert "STT_PROVIDER" in (reply.next_step_hint or "")


async def test_orchestrator_audio_fallback_with_transcriber(tmp_path: Path) -> None:
    """Verify non-audio LLM transcribes audio via STT and persists text turn."""
    db = Database(tmp_path / "orch_stt.db")
    await db.init()

    provider = FakeProvider(supports_native_audio=False)
    orchestrator = AgentOrchestrator(
        provider=provider,
        database=db,
        timezone_name="America/Sao_Paulo",
        transcriber=FakeTranscriber(),  # type: ignore[arg-type]
    )

    reply = await orchestrator.process_message(
        user_id=123,
        attachments=[MediaAttachment(kind="audio", mime_type="audio/ogg", data=b"ogg")],
    )
    assert reply.intent == "action_result"
    assert "[Áudio transcrito]: Abasteci duzentos reais" in (provider.last_user_text or "")
    history = await db.get_recent_messages(123)
    assert len(history) == 2
