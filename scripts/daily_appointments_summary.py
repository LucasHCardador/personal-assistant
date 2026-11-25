"""Standalone script to send the daily appointments summary (text + audio) via Telegram."""

import asyncio
import io
import logging
import sys
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from telegram import Bot

from src.agent.tts import SpeechSynthesizer
from src.config import Settings, get_settings
from src.integrations.google_auth import load_google_credentials
from src.integrations.google_calendar import GoogleCalendarService

logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    """Configure structured logging while keeping HTTP client URLs silent."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _parse_event_datetime(iso_str: str, timezone_name: str) -> datetime:
    """Parse an ISO-8601 datetime string into the target local timezone."""
    parsed = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    tz = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def format_event_description(event: dict[str, Any]) -> str:
    """Return the event summary, appending location when available and not redundant."""
    summary = str(event.get("summary") or "(Sem título)").strip()
    location = str(event.get("location") or "").strip()
    if location and location.lower() not in summary.lower():
        return f"{summary} em {location}"
    return summary


def format_text_time(start_str: str, timezone_name: str) -> str:
    """Format an event start time for the written summary."""
    if not start_str or "T" not in start_str:
        return "Dia todo"
    local_dt = _parse_event_datetime(start_str, timezone_name)
    if local_dt.minute == 0:
        return f"Às {local_dt.hour:02d} horas"
    return f"Às {local_dt.hour:02d}:{local_dt.minute:02d}"


def format_audio_time(start_str: str, timezone_name: str) -> str:
    """Format an event start time for natural Portuguese TTS pronunciation."""
    if not start_str or "T" not in start_str:
        return "Durante o dia todo"
    local_dt = _parse_event_datetime(start_str, timezone_name)
    if local_dt.minute == 0:
        return f"Às {local_dt.hour} horas"
    if local_dt.minute == 30:
        return f"Às {local_dt.hour} e meia"
    return f"Às {local_dt.hour} e {local_dt.minute}"


def format_appointments_text(events: list[dict[str, Any]], timezone_name: str) -> str:
    """Render the daily appointments text summary matching the required bullet format."""
    if not events:
        return "Compromissos de hoje:\nNenhum compromisso agendado."

    lines = ["Compromissos de hoje:"]
    last_index = len(events) - 1
    for idx, event in enumerate(events):
        time_label = format_text_time(str(event.get("start") or ""), timezone_name)
        description = format_event_description(event)
        suffix = ";" if idx < last_index else ""
        lines.append(f"* {time_label}, {description}{suffix}")
    return "\n".join(lines)


def format_appointments_audio_text(events: list[dict[str, Any]], timezone_name: str) -> str:
    """Render the daily appointments script formatted for TTS audio synthesis."""
    if not events:
        return "Compromissos de hoje: nenhum compromisso agendado."

    lines = ["Compromissos de hoje:"]
    for event in events:
        time_label = format_audio_time(str(event.get("start") or ""), timezone_name)
        description = format_event_description(event)
        lines.append(f"{time_label}, {description}.")
    return "\n".join(lines)


def _build_calendar_service(settings: Settings) -> GoogleCalendarService:
    """Load OAuth credentials and build GoogleCalendarService."""
    creds = load_google_credentials(
        settings.google_credentials_path,
        settings.google_token_path,
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return GoogleCalendarService(service=service, timezone_name=settings.timezone)


async def send_daily_appointments_summary(
    *,
    settings: Settings | None = None,
    calendar_service: GoogleCalendarService | None = None,
    tts: SpeechSynthesizer | None = None,
    bot: Bot | None = None,
    now: datetime | None = None,
) -> None:
    """Fetch today's Google Calendar events and send text + voice summary to allowed users."""
    cfg = settings or get_settings()
    if not cfg.telegram_allowed_user_ids:
        logger.warning("TELEGRAM_ALLOWED_USER_IDS is empty; skipping daily appointments summary.")
        return

    tz = ZoneInfo(cfg.timezone)
    now_local = now.astimezone(tz) if now else datetime.now(tz)
    today = now_local.date()
    start_of_day = datetime.combine(today, time.min, tzinfo=tz).isoformat()
    end_of_day = datetime.combine(today, time.max, tzinfo=tz).isoformat()

    cal = calendar_service or _build_calendar_service(cfg)
    cal_result = await cal.list_events(
        start_iso=start_of_day,
        end_iso=end_of_day,
        max_results=50,
    )
    events = cal_result.get("events", []) if cal_result.get("status") == "ok" else []

    text_message = format_appointments_text(events, cfg.timezone)
    audio_script = format_appointments_audio_text(events, cfg.timezone)

    synthesizer = tts or SpeechSynthesizer(voice=cfg.tts_voice)
    audio_bytes = await synthesizer.synthesize(audio_script)

    async def _deliver(target_bot: Bot) -> None:
        for user_id in cfg.telegram_allowed_user_ids:
            await target_bot.send_message(chat_id=user_id, text=text_message)
            voice_buffer = io.BytesIO(audio_bytes)
            try:
                await target_bot.send_voice(
                    chat_id=user_id,
                    voice=voice_buffer,
                    filename="compromissos-hoje.mp3",
                )
            finally:
                voice_buffer.close()
        logger.info(
            "Daily appointments summary sent to %d user(s) (%d event(s)).",
            len(cfg.telegram_allowed_user_ids),
            len(events),
        )

    if bot is not None:
        await _deliver(bot)
        return

    async with Bot(token=cfg.telegram_bot_token) as managed_bot:
        await _deliver(managed_bot)


def main() -> None:
    """CLI entrypoint for crontab execution."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Running daily appointments summary cron job...")
    asyncio.run(send_daily_appointments_summary(settings=settings))


if __name__ == "__main__":
    main()
