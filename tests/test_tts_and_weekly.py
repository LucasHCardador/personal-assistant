"""Unit tests for TTS audio summaries and weekly proactive summary."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.agent.schemas import AssistantStructuredReply
from src.agent.tts import html_to_speech_text
from src.bot.handlers import BotHandlers
from src.config import Settings
from src.scheduler.proactive import ProactiveNotifier, register_proactive_jobs
from src.storage.database import Database


class FakeTTS:
    """Test double for SpeechSynthesizer returning deterministic audio bytes."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return b"fake-mp3-bytes"


def test_html_to_speech_text_cleans_tags_and_emojis() -> None:
    """Verify HTML tags, entities, and emojis are stripped for natural TTS reading."""
    raw = "✅ <b>Resumo da Semana</b>\n• Consulta &amp; Exame <i>14:00</i>"
    cleaned = html_to_speech_text(raw)
    assert "<" not in cleaned
    assert "&amp;" not in cleaned
    assert "Resumo da Semana" in cleaned
    assert "Consulta & Exame 14:00" in cleaned


async def test_bot_handler_sends_voice_when_send_as_audio_true(tmp_path: Path) -> None:
    """Verify BotHandlers replies with voice alongside text when send_as_audio is True."""
    db = Database(tmp_path / "tts_bot.db")
    await db.init()

    fake_orchestrator = SimpleNamespace(
        process_message=AsyncMock(
            return_value=AssistantStructuredReply(
                intent="chat",
                summary="Resumo dos seus compromissos da semana",
                details=["Segunda 10:00 - Reunião"],
                send_as_audio=True,
            )
        )
    )
    fake_tts = FakeTTS()
    handlers = BotHandlers(
        allowed_user_ids=[123],
        orchestrator=fake_orchestrator,  # type: ignore[arg-type]
        database=db,
        tts=fake_tts,  # type: ignore[arg-type]
    )

    message = SimpleNamespace(
        text="Me manda o resumo da semana em áudio",
        reply_text=AsyncMock(),
        reply_voice=AsyncMock(),
        chat=SimpleNamespace(send_action=AsyncMock()),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=message,
    )

    await handlers.text_message(update, SimpleNamespace())  # type: ignore[arg-type]

    message.reply_text.assert_awaited_once()
    message.reply_voice.assert_awaited_once()
    assert len(fake_tts.calls) == 1


async def test_proactive_daily_and_weekly_summaries_send_voice(tmp_path: Path) -> None:
    """Verify morning and weekly proactive summaries send both HTML text and voice."""
    db = Database(tmp_path / "tts_proactive.db")
    await db.init()

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        telegram_bot_token="dummy-token",
        telegram_allowed_user_ids=[123],
    )
    bot = SimpleNamespace(send_message=AsyncMock(), send_voice=AsyncMock())
    calendar_service = SimpleNamespace(
        list_events=AsyncMock(
            return_value={
                "status": "ok",
                "events": [
                    {
                        "id": "ev-1",
                        "summary": "Culto na Igreja",
                        "start": "2026-11-29T19:00:00-03:00",
                    }
                ],
            }
        )
    )
    fake_tts = FakeTTS()

    notifier = ProactiveNotifier(
        bot=bot,  # type: ignore[arg-type]
        database=db,
        settings=settings,
        calendar_service=calendar_service,  # type: ignore[arg-type]
        tts=fake_tts,  # type: ignore[arg-type]
    )

    now = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
    await notifier.send_morning_summary(now=now)
    await notifier.send_weekly_summary(now=now)

    assert bot.send_message.await_count == 2
    assert bot.send_voice.await_count == 2
    assert len(fake_tts.calls) == 2

    scheduler = AsyncIOScheduler()
    register_proactive_jobs(scheduler, notifier, settings)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "proactive_weekly_summary" in job_ids
