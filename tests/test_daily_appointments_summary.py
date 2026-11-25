"""Unit tests for the dedicated daily appointments summary cron script."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from scripts.daily_appointments_summary import (
    format_appointments_audio_text,
    format_appointments_text,
    format_audio_time,
    format_text_time,
    send_daily_appointments_summary,
)
from src.config import Settings

TZ = "America/Sao_Paulo"


def test_format_appointments_text_matches_user_example() -> None:
    """Verify exact bullet formatting, hours/minutes, and semicolons on all but last item."""
    events = [
        {
            "start": "2026-11-25T07:00:00-03:00",
            "summary": "tomografia do Noah na Unimed Londrina",
            "location": "",
        },
        {
            "start": "2026-11-25T08:00:00-03:00",
            "summary": "fisioterapia do Noah na ABAKIDS",
            "location": "",
        },
        {
            "start": "2026-11-25T16:30:00-03:00",
            "summary": "consulta com hematologista do Davi no Centro de Uncologia de Londrina",
            "location": "",
        },
        {
            "start": "2026-11-25T20:00:00-03:00",
            "summary": "aniversário da Lara no Salão de festas",
            "location": "",
        },
    ]

    expected = (
        "Compromissos de hoje:\n"
        "* Às 07 horas, tomografia do Noah na Unimed Londrina;\n"
        "* Às 08 horas, fisioterapia do Noah na ABAKIDS;\n"
        "* Às 16:30, consulta com hematologista do Davi no Centro de Uncologia de Londrina;\n"
        "* Às 20 horas, aniversário da Lara no Salão de festas"
    )
    assert format_appointments_text(events, TZ) == expected


def test_format_audio_time_guidelines() -> None:
    """Verify TTS time rules: full hours, ':30' as 'e meia', and other minutes as 'e MM'."""
    assert format_audio_time("2026-11-25T07:00:00-03:00", TZ) == "Às 07 horas"
    assert format_audio_time("2026-11-25T13:00:00-03:00", TZ) == "Às 13 horas"
    assert format_audio_time("2026-11-25T20:00:00-03:00", TZ) == "Às 20 horas"
    assert format_audio_time("2026-11-25T16:30:00-03:00", TZ) == "Às 16 e meia"
    assert format_audio_time("2026-11-25T16:23:00-03:00", TZ) == "Às 16 e 23"
    assert format_audio_time("2026-11-25T09:05:00-03:00", TZ) == "Às 09 e 5"
    assert format_audio_time("2026-11-25", TZ) == "Durante o dia todo"


def test_format_text_time_and_location_handling() -> None:
    """Verify location is appended only when non-empty and not already in summary."""
    assert format_text_time("2026-11-25T16:23:00-03:00", TZ) == "Às 16:23"
    assert format_text_time("2026-11-25", TZ) == "Dia todo"

    events = [
        {
            "start": "2026-11-25T10:00:00-03:00",
            "summary": "Reunião de alinhamento",
            "location": "Sala 2",
        },
        {
            "start": "2026-11-25T14:30:00-03:00",
            "summary": "Consulta no Hospital Central",
            "location": "Hospital Central",
        },
    ]
    text = format_appointments_text(events, TZ)
    assert "* Às 10 horas, Reunião de alinhamento em Sala 2;" in text
    assert text.endswith("* Às 14:30, Consulta no Hospital Central")

    audio = format_appointments_audio_text(events, TZ)
    assert "Às 10 horas, Reunião de alinhamento em Sala 2." in audio
    assert "Às 14 e meia, Consulta no Hospital Central." in audio


def test_format_empty_events() -> None:
    """Verify clean output when there are no appointments for today."""
    assert (
        format_appointments_text([], TZ)
        == "Compromissos de hoje:\nNenhum compromisso agendado."
    )
    assert (
        format_appointments_audio_text([], TZ)
        == "Compromissos de hoje: nenhum compromisso agendado."
    )


async def test_send_daily_appointments_summary_dispatches_text_and_voice() -> None:
    """Verify the cron job fetches today's events and sends both text and voice to all users."""
    settings = Settings(
        telegram_bot_token="123:test-token",
        telegram_allowed_user_ids=[101, 202],
        timezone=TZ,
    )
    events = [
        {
            "start": "2026-11-25T07:00:00-03:00",
            "summary": "tomografia do Noah na Unimed Londrina",
            "location": "",
        },
        {
            "start": "2026-11-25T16:30:00-03:00",
            "summary": "consulta do Davi",
            "location": "Clínica",
        },
    ]
    fake_calendar = SimpleNamespace(
        list_events=AsyncMock(return_value={"status": "ok", "events": events})
    )
    fake_tts = SimpleNamespace(synthesize=AsyncMock(return_value=b"fake-mp3-data"))
    fake_bot = SimpleNamespace(
        send_message=AsyncMock(),
        send_voice=AsyncMock(),
    )

    now = datetime(2026, 11, 25, 7, 30, tzinfo=ZoneInfo(TZ))
    await send_daily_appointments_summary(
        settings=settings,
        calendar_service=fake_calendar,  # type: ignore[arg-type]
        tts=fake_tts,  # type: ignore[arg-type]
        bot=fake_bot,  # type: ignore[arg-type]
        now=now,
    )

    fake_calendar.list_events.assert_awaited_once()
    fake_tts.synthesize.assert_awaited_once()
    tts_input = fake_tts.synthesize.await_args.args[0]
    assert "Às 07 horas, tomografia do Noah na Unimed Londrina." in tts_input
    assert "Às 16 e meia, consulta do Davi em Clínica." in tts_input

    assert fake_bot.send_message.await_count == 2
    assert fake_bot.send_voice.await_count == 2
