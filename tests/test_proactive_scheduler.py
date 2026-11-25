"""Unit tests for reminders persistence, tools, and proactive scheduler."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.agent.tools import ToolExecutor, ToolRegistry
from src.config import Settings
from src.scheduler.proactive import ProactiveNotifier, register_proactive_jobs
from src.storage.database import Database


def _make_settings(tmp_path: Path, allowed_ids: list[int] | None = None) -> Settings:
    return Settings(
        telegram_bot_token="test-token",
        telegram_allowed_user_ids=allowed_ids if allowed_ids is not None else [111, 222],
        database_path=tmp_path / "assistant.db",
        timezone="America/Sao_Paulo",
        morning_summary_time="07:30",
    )


async def test_database_reminders_crud_and_recurrence(tmp_path: Path) -> None:
    """Verify reminder creation, listing, cancellation, due lookup, and recurrence."""
    db = Database(tmp_path / "reminders.db")
    await db.init()

    once_id = await db.create_reminder(
        user_id=10,
        title="Pagar fatura",
        trigger_at="2026-01-31T12:00:00+00:00",
        recurrence="once",
    )
    daily_id = await db.create_reminder(
        user_id=10,
        title="Tomar vitamina",
        trigger_at="2026-01-31T08:00:00-03:00",
        recurrence="daily",
    )
    weekly_id = await db.create_reminder(
        user_id=10,
        title="Revisar metas",
        trigger_at="2026-01-31T10:00:00+00:00",
        recurrence="weekly",
    )
    monthly_id = await db.create_reminder(
        user_id=10,
        title="Fechar orçamento",
        trigger_at="2026-01-31T09:00:00+00:00",
        recurrence="monthly",
    )

    pending = await db.list_reminders(user_id=10, status="pending")
    assert len(pending) == 4
    assert pending[0].id == monthly_id  # 09:00 UTC is earliest

    # At 11:30 UTC, 08:00-03:00 (=11:00 UTC), 09:00 UTC, 10:00 UTC are due; 12:00 UTC is not.
    due = await db.get_due_reminders(now_iso="2026-01-31T11:30:00+00:00")
    assert {r.id for r in due} == {daily_id, weekly_id, monthly_id}

    assert await db.mark_reminder_dispatched(once_id) is True
    assert await db.mark_reminder_dispatched(daily_id) is True
    assert await db.mark_reminder_dispatched(weekly_id) is True
    assert await db.mark_reminder_dispatched(monthly_id) is True

    sent_list = await db.list_reminders(user_id=10, status="sent")
    assert [r.id for r in sent_list] == [once_id]

    updated_pending = {r.id: r for r in await db.list_reminders(user_id=10, status="pending")}
    assert updated_pending[daily_id].trigger_at == "2026-02-01T08:00:00-03:00"
    assert updated_pending[weekly_id].trigger_at == "2026-02-07T10:00:00+00:00"
    # Jan 31 + 1 month clamps to Feb 28 in non-leap year 2026.
    assert updated_pending[monthly_id].trigger_at == "2026-02-28T09:00:00+00:00"

    assert await db.cancel_reminder(daily_id, user_id=999) is False
    assert await db.cancel_reminder(daily_id, user_id=10) is True
    assert await db.cancel_reminder(daily_id, user_id=10) is False


async def test_database_sent_notifications_deduplication(tmp_path: Path) -> None:
    """Verify sent_notifications tracks keys idempotently."""
    db = Database(tmp_path / "notif.db")
    await db.init()

    key = "cal:evt-1:1h:2026-11-24"
    assert await db.has_notification_been_sent(key) is False
    await db.mark_notification_sent(key)
    await db.mark_notification_sent(key)
    assert await db.has_notification_been_sent(key) is True


async def test_tool_registry_and_executor_reminders(tmp_path: Path) -> None:
    """Verify reminder tools are always enabled and executed via ToolExecutor."""
    registry = ToolRegistry()
    names = {tool.name for tool in registry.definitions}
    assert {"create_reminder", "list_reminders", "cancel_reminder"} <= names

    db = Database(tmp_path / "tools.db")
    await db.init()
    executor = ToolExecutor(database=db, timezone_name="America/Sao_Paulo")

    created = await executor.execute(
        user_id=111,
        tool_name="create_reminder",
        arguments={
            "title": "Comprar café",
            "trigger_at_iso": "2026-11-24T09:00:00",
            "recurrence": "weekly",
        },
    )
    assert created["status"] == "ok"
    assert created["trigger_at"] == "2026-11-24T09:00:00-03:00"
    reminder_id = created["reminder_id"]

    listed = await executor.execute(
        user_id=111,
        tool_name="list_reminders",
        arguments={"status": "pending"},
    )
    assert listed["status"] == "ok"
    assert listed["count"] == 1
    assert listed["reminders"][0]["title"] == "Comprar café"

    cancelled = await executor.execute(
        user_id=111,
        tool_name="cancel_reminder",
        arguments={"reminder_id": reminder_id},
    )
    assert cancelled["status"] == "ok"

    missing = await executor.execute(
        user_id=111,
        tool_name="cancel_reminder",
        arguments={"reminder_id": reminder_id},
    )
    assert missing["status"] == "not_found"


async def test_proactive_morning_summary_and_reminders_dispatch(tmp_path: Path) -> None:
    """Verify morning summary aggregation and reminder dispatch with mocked Bot."""
    settings = _make_settings(tmp_path, allowed_ids=[111])
    db = Database(settings.database_path)
    await db.init()

    tz = ZoneInfo("America/Sao_Paulo")
    await db.create_reminder(
        user_id=111,
        title="Levar exame <urgente>",
        trigger_at=datetime(2026, 11, 24, 9, 0, tzinfo=tz).isoformat(),
        recurrence="once",
    )
    await db.create_reminder(
        user_id=111,
        title="Lembrete futuro",
        trigger_at=datetime(2026, 11, 25, 9, 0, tzinfo=tz).isoformat(),
        recurrence="once",
    )

    mock_bot = SimpleNamespace(send_message=AsyncMock())
    mock_calendar = SimpleNamespace(
        list_events=AsyncMock(
            return_value={
                "status": "ok",
                "events": [
                    {
                        "id": "e1",
                        "summary": "Reunião <Equipe>",
                        "start": "2026-11-24T10:00:00-03:00",
                        "meet_link": "https://meet.google.com/abc-defg-hij",
                    }
                ],
            }
        )
    )
    mock_sheets = SimpleNamespace(
        has_car_sheet=True,
        get_car_maintenance_status=AsyncMock(
            return_value={
                "status": "ok",
                "current_km": 49500,
                "items": [
                    {
                        "item": "Troca de óleo",
                        "next_km": 50000,
                        "next_date": None,
                        "status": "Próximo (500 km restantes)",
                    },
                    {
                        "item": "Filtro de ar",
                        "next_km": 60000,
                        "next_date": None,
                        "status": "Pendente",
                    },
                ],
            }
        ),
    )

    notifier = ProactiveNotifier(
        bot=mock_bot,  # type: ignore[arg-type]
        database=db,
        settings=settings,
        calendar_service=mock_calendar,  # type: ignore[arg-type]
        sheets_service=mock_sheets,  # type: ignore[arg-type]
    )

    await notifier.send_morning_summary(now=datetime(2026, 11, 24, 7, 30, tzinfo=tz))
    mock_bot.send_message.assert_awaited_once()
    sent_text = mock_bot.send_message.await_args.kwargs["text"]
    assert "Resumo Matinal — 24/11/2026" in sent_text
    assert "Reunião &lt;Equipe&gt;" in sent_text
    assert "Levar exame &lt;urgente&gt;" in sent_text
    assert "Lembrete futuro" not in sent_text
    assert "Troca de óleo" in sent_text
    assert "Filtro de ar" not in sent_text

    mock_bot.send_message.reset_mock()
    await notifier.dispatch_due_reminders(now=datetime(2026, 11, 24, 9, 5, tzinfo=tz))
    mock_bot.send_message.assert_awaited_once()
    assert "Levar exame &lt;urgente&gt;" in mock_bot.send_message.await_args.kwargs["text"]
    assert len(await db.list_reminders(user_id=111, status="sent")) == 1


async def test_proactive_upcoming_events_and_maintenance_dedup(tmp_path: Path) -> None:
    """Verify 1h/24h event alerts and car maintenance alerts do not duplicate."""
    settings = _make_settings(tmp_path, allowed_ids=[111, 222])
    db = Database(settings.database_path)
    await db.init()

    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime(2026, 11, 24, 9, 0, tzinfo=tz)

    mock_bot = SimpleNamespace(send_message=AsyncMock())
    mock_calendar = SimpleNamespace(
        list_events=AsyncMock(
            return_value={
                "status": "ok",
                "events": [
                    {
                        "id": "evt-1h",
                        "summary": "Consulta",
                        "start": "2026-11-24T10:00:00-03:00",
                        "location": "Clínica",
                        "meet_link": "",
                    },
                    {
                        "id": "evt-24h",
                        "summary": "Culto",
                        "start": "2026-11-25T08:30:00-03:00",
                        "location": "",
                        "meet_link": "",
                    },
                    {
                        "id": "evt-allday",
                        "summary": "Feriado",
                        "start": "2026-11-24",
                    },
                ],
            }
        )
    )
    mock_sheets = SimpleNamespace(
        has_car_sheet=True,
        get_car_maintenance_status=AsyncMock(
            return_value={
                "status": "ok",
                "current_km": 50200,
                "items": [
                    {
                        "item": "Troca de óleo",
                        "next_km": 50000,
                        "next_date": None,
                        "status": "Vencido (Km)",
                    },
                    {
                        "item": "Alinhamento",
                        "next_km": None,
                        "next_date": "2026-12-20",
                        "status": "Próximo (26 dias restantes)",
                    },
                ],
            }
        ),
    )

    notifier = ProactiveNotifier(
        bot=mock_bot,  # type: ignore[arg-type]
        database=db,
        settings=settings,
        calendar_service=mock_calendar,  # type: ignore[arg-type]
        sheets_service=mock_sheets,  # type: ignore[arg-type]
    )

    await notifier.check_upcoming_events(now=now)
    # 2 timed events x 2 allowed users = 4 messages; all-day event is skipped.
    assert mock_bot.send_message.await_count == 4

    mock_bot.send_message.reset_mock()
    await notifier.check_upcoming_events(now=now)
    assert mock_bot.send_message.await_count == 0

    await notifier.check_car_maintenance(now=now)
    # Only overdue item ("Troca de óleo") triggers; 26 days out (> 15) does not.
    assert mock_bot.send_message.await_count == 2
    maint_text = mock_bot.send_message.await_args.kwargs["text"]
    assert "Troca de óleo" in maint_text
    assert "Alinhamento" not in maint_text

    mock_bot.send_message.reset_mock()
    await notifier.check_car_maintenance(now=now)
    assert mock_bot.send_message.await_count == 0


async def test_dispatch_due_reminders_does_not_mark_on_send_failure(tmp_path: Path) -> None:
    """Verify reminder remains pending if Telegram send_message raises."""
    settings = _make_settings(tmp_path, allowed_ids=[111])
    db = Database(settings.database_path)
    await db.init()
    await db.create_reminder(
        user_id=111,
        title="Não perder",
        trigger_at="2026-11-24T10:00:00+00:00",
        recurrence="once",
    )

    mock_bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("network error")))
    notifier = ProactiveNotifier(bot=mock_bot, database=db, settings=settings)  # type: ignore[arg-type]

    await notifier.dispatch_due_reminders(now=datetime(2026, 11, 24, 10, 5, tzinfo=UTC))
    pending = await db.list_reminders(user_id=111, status="pending")
    assert len(pending) == 1


def test_register_proactive_jobs_adds_all_jobs(tmp_path: Path) -> None:
    """Verify register_proactive_jobs schedules all 4 proactive jobs."""
    settings = _make_settings(tmp_path)
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.timezone))
    notifier = ProactiveNotifier(
        bot=SimpleNamespace(send_message=AsyncMock()),  # type: ignore[arg-type]
        database=Database(settings.database_path),
        settings=settings,
    )

    register_proactive_jobs(scheduler, notifier, settings)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {
        "proactive_morning_summary",
        "proactive_upcoming_events",
        "proactive_car_maintenance",
        "proactive_due_reminders",
        "proactive_weekly_summary",
    }
