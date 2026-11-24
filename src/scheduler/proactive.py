"""Proactive notification engine scheduled via APScheduler."""

import io
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode

from src.agent.tts import SpeechSynthesizer
from src.bot.formatters import (
    format_event_alert,
    format_maintenance_alert,
    format_morning_summary,
    format_reminder_notification,
    format_weekly_summary,
)
from src.config import Settings
from src.integrations.google_calendar import GoogleCalendarService
from src.integrations.google_sheets import GoogleSheetsService
from src.storage.database import Database

logger = logging.getLogger(__name__)


def _parse_iso(value: str, default_tz: ZoneInfo) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=default_tz)
    return parsed


def _is_alertable_maintenance_item(item: dict[str, Any], today: date) -> bool:
    """Return True when a maintenance item is overdue or due within 1000 km / 15 days."""
    status = str(item.get("status") or "").lower()
    if "vencido" in status:
        return True
    if "próximo" not in status:
        return False

    next_date_str = str(item.get("next_date") or "").strip()
    if next_date_str:
        try:
            next_dt = datetime.strptime(next_date_str, "%Y-%m-%d").date()
            if (next_dt - today).days <= 15:
                return True
        except ValueError:
            pass

    return "km restantes" in status


class ProactiveNotifier:
    """Executes proactive scheduled checks and sends Telegram notifications."""

    def __init__(
        self,
        *,
        bot: Bot,
        database: Database,
        settings: Settings,
        calendar_service: GoogleCalendarService | None = None,
        sheets_service: GoogleSheetsService | None = None,
        tts: SpeechSynthesizer | None = None,
    ) -> None:
        self._bot = bot
        self._db = database
        self._settings = settings
        self._calendar = calendar_service
        self._sheets = sheets_service
        self._tts = tts
        self._tz = ZoneInfo(settings.timezone)

    async def _send_voice(self, user_id: int, html_text: str, filename: str) -> None:
        """Synthesize and send an in-memory voice message, logging failures gracefully."""
        if self._tts is None:
            return
        try:
            audio_bytes = await self._tts.synthesize(html_text)
            buf = io.BytesIO(audio_bytes)
            try:
                await self._bot.send_voice(chat_id=user_id, voice=buf, filename=filename)
            finally:
                buf.close()
        except Exception as exc:
            logger.warning("Failed to send proactive voice to user %s: %s", user_id, exc)

    async def _send_html(self, user_id: int, text: str) -> bool:
        """Send an HTML message to a single Telegram user, logging failures."""
        try:
            await self._bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send proactive message to user %s: %s", user_id, exc)
            return False

    async def _broadcast_html(self, text: str) -> None:
        """Send an HTML message to every authorized Telegram user."""
        for user_id in self._settings.telegram_allowed_user_ids:
            await self._send_html(user_id, text)

    async def _fetch_alertable_maintenance(
        self,
        today: date,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch overdue or imminent vehicle maintenance items if car sheet is enabled."""
        if self._sheets is None or not self._sheets.has_car_sheet:
            return [], None

        try:
            result = await self._sheets.get_car_maintenance_status()
        except Exception as exc:
            logger.warning("Failed to fetch car maintenance status: %s", exc)
            return [], None

        if result.get("status") != "ok":
            return [], None

        items = [
            item
            for item in result.get("items", [])
            if _is_alertable_maintenance_item(item, today)
        ]
        return items, result.get("current_km")

    async def send_morning_summary(self, now: datetime | None = None) -> None:
        """Send the daily morning summary to all authorized users."""
        if not self._settings.telegram_allowed_user_ids:
            return

        now_local = now.astimezone(self._tz) if now else datetime.now(self._tz)
        today = now_local.date()
        date_label = today.strftime("%d/%m/%Y")

        events: list[dict[str, Any]] = []
        if self._calendar is not None:
            start_of_day = datetime.combine(today, time.min, tzinfo=self._tz).isoformat()
            end_of_day = datetime.combine(today, time.max, tzinfo=self._tz).isoformat()
            try:
                cal_result = await self._calendar.list_events(
                    start_iso=start_of_day,
                    end_iso=end_of_day,
                )
                if cal_result.get("status") == "ok":
                    events = cal_result.get("events", [])
            except Exception as exc:
                logger.warning("Failed to fetch today's calendar events: %s", exc)

        maintenance_items, _ = await self._fetch_alertable_maintenance(today)

        for user_id in self._settings.telegram_allowed_user_ids:
            pending = await self._db.list_reminders(user_id=user_id, status="pending")
            today_reminders = [
                reminder
                for reminder in pending
                if _parse_iso(reminder.trigger_at, self._tz).astimezone(self._tz).date() <= today
            ]
            message = format_morning_summary(
                date_label=date_label,
                events=events,
                reminders=today_reminders,
                maintenance_items=maintenance_items,
                timezone_name=self._settings.timezone,
            )
            await self._send_html(user_id, message)
            await self._send_voice(user_id, message, filename="resumo-diario.mp3")

    async def send_weekly_summary(self, now: datetime | None = None) -> None:
        """Send the weekly overview (text + voice) to all authorized users."""
        if not self._settings.telegram_allowed_user_ids:
            return

        now_local = now.astimezone(self._tz) if now else datetime.now(self._tz)
        start_date = now_local.date()
        end_date = start_date + timedelta(days=7)
        period_label = f"{start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')}"

        events: list[dict[str, Any]] = []
        if self._calendar is not None:
            start_iso = datetime.combine(start_date, time.min, tzinfo=self._tz).isoformat()
            end_iso = datetime.combine(end_date, time.max, tzinfo=self._tz).isoformat()
            try:
                cal_result = await self._calendar.list_events(
                    start_iso=start_iso,
                    end_iso=end_iso,
                    max_results=50,
                )
                if cal_result.get("status") == "ok":
                    events = cal_result.get("events", [])
            except Exception as exc:
                logger.warning("Failed to fetch weekly calendar events: %s", exc)

        maintenance_items, _ = await self._fetch_alertable_maintenance(start_date)

        for user_id in self._settings.telegram_allowed_user_ids:
            pending = await self._db.list_reminders(user_id=user_id, status="pending")
            week_reminders = [
                reminder
                for reminder in pending
                if _parse_iso(reminder.trigger_at, self._tz).astimezone(self._tz).date()
                <= end_date
            ]
            message = format_weekly_summary(
                period_label=period_label,
                events=events,
                reminders=week_reminders,
                maintenance_items=maintenance_items,
                timezone_name=self._settings.timezone,
            )
            await self._send_html(user_id, message)
            await self._send_voice(user_id, message, filename="resumo-semanal.mp3")

    async def check_upcoming_events(self, now: datetime | None = None) -> None:
        """Notify authorized users 24h and 1h before upcoming calendar events."""
        if self._calendar is None or not self._settings.telegram_allowed_user_ids:
            return

        now_local = now.astimezone(self._tz) if now else datetime.now(self._tz)
        start_iso = now_local.isoformat()
        end_iso = (now_local + timedelta(hours=24, minutes=5)).isoformat()

        try:
            cal_result = await self._calendar.list_events(start_iso=start_iso, end_iso=end_iso)
        except Exception as exc:
            logger.warning("Failed to check upcoming calendar events: %s", exc)
            return

        if cal_result.get("status") != "ok":
            return

        for event in cal_result.get("events", []):
            start_str = str(event.get("start") or "")
            # Skip all-day events (YYYY-MM-DD) for timed 1h/24h alerts.
            if not start_str or "T" not in start_str:
                continue

            start_dt = _parse_iso(start_str, self._tz)
            minutes_until = (start_dt - now_local).total_seconds() / 60.0

            if 50 <= minutes_until <= 65:
                window_key, window_label = "1h", "em 1 hora"
            elif 23 * 60 <= minutes_until <= 24 * 60:
                window_key, window_label = "24h", "amanhã"
            else:
                continue

            event_id = str(event.get("id") or event.get("summary") or "")
            notif_key = f"cal:{event_id}:{window_key}:{start_dt.date().isoformat()}"
            if await self._db.has_notification_been_sent(notif_key):
                continue

            message = format_event_alert(
                event=event,
                window_label=window_label,
                timezone_name=self._settings.timezone,
            )
            await self._broadcast_html(message)
            await self._db.mark_notification_sent(notif_key)

    async def check_car_maintenance(self, now: datetime | None = None) -> None:
        """Notify authorized users about overdue or imminent car maintenance items."""
        if not self._settings.telegram_allowed_user_ids:
            return

        now_local = now.astimezone(self._tz) if now else datetime.now(self._tz)
        today = now_local.date()
        today_iso = today.isoformat()

        alertable_items, current_km = await self._fetch_alertable_maintenance(today)
        if not alertable_items:
            return

        unsent_items: list[dict[str, Any]] = []
        unsent_keys: list[str] = []
        for item in alertable_items:
            key = f"car_maint:{item.get('item', '')}:{item.get('status', '')}:{today_iso}"
            if not await self._db.has_notification_been_sent(key):
                unsent_items.append(item)
                unsent_keys.append(key)

        if not unsent_items:
            return

        message = format_maintenance_alert(items=unsent_items, current_km=current_km)
        await self._broadcast_html(message)
        for key in unsent_keys:
            await self._db.mark_notification_sent(key)

    async def dispatch_due_reminders(self, now: datetime | None = None) -> None:
        """Dispatch due user reminders and advance or complete them in SQLite."""
        now_utc = now.astimezone(UTC) if now else datetime.now(UTC)
        due_reminders = await self._db.get_due_reminders(now_iso=now_utc.isoformat())
        for reminder in due_reminders:
            message = format_reminder_notification(
                reminder=reminder,
                timezone_name=self._settings.timezone,
            )
            sent = await self._send_html(reminder.user_id, message)
            if sent:
                await self._db.mark_reminder_dispatched(reminder.id)


def register_proactive_jobs(
    scheduler: AsyncIOScheduler,
    notifier: ProactiveNotifier,
    settings: Settings,
) -> None:
    """Register all proactive notification jobs on the given APScheduler instance."""
    hour_str, minute_str = settings.morning_summary_time.split(":")
    tz = ZoneInfo(settings.timezone)

    scheduler.add_job(
        notifier.send_morning_summary,
        trigger="cron",
        hour=int(hour_str),
        minute=int(minute_str),
        timezone=tz,
        id="proactive_morning_summary",
        replace_existing=True,
    )
    scheduler.add_job(
        notifier.check_upcoming_events,
        trigger="interval",
        minutes=5,
        id="proactive_upcoming_events",
        replace_existing=True,
    )
    scheduler.add_job(
        notifier.check_car_maintenance,
        trigger="cron",
        hour=int(hour_str),
        minute=int(minute_str),
        timezone=tz,
        id="proactive_car_maintenance",
        replace_existing=True,
    )
    scheduler.add_job(
        notifier.dispatch_due_reminders,
        trigger="interval",
        minutes=1,
        id="proactive_due_reminders",
        replace_existing=True,
    )
    weekly_hour_str, weekly_minute_str = settings.weekly_summary_time.split(":")
    scheduler.add_job(
        notifier.send_weekly_summary,
        trigger="cron",
        day_of_week=settings.weekly_summary_day,
        hour=int(weekly_hour_str),
        minute=int(weekly_minute_str),
        timezone=tz,
        id="proactive_weekly_summary",
        replace_existing=True,
    )
