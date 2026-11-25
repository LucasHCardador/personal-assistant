"""Unit tests for Google Calendar, Google Meet, pending confirmations, and inline callbacks."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiosqlite

from src.agent.orchestrator import AgentOrchestrator
from src.agent.providers.base import BaseLLMProvider, ToolCaller
from src.agent.schemas import (
    AssistantStructuredReply,
    ChatMessage,
    MediaAttachment,
    ToolDefinition,
)
from src.agent.tools import ToolExecutor, ToolRegistry
from src.bot.handlers import BotHandlers
from src.integrations.google_calendar import GoogleCalendarService
from src.storage.database import Database


def _make_mock_calendar_api() -> MagicMock:
    """Build a mock googleapiclient Calendar v3 resource."""
    service = MagicMock()
    events_resource = MagicMock()
    service.events.return_value = events_resource
    return service


async def test_google_calendar_list_and_create_meet_event() -> None:
    """Verify list_events and create_event with conferenceData hangoutsMeet."""
    api = _make_mock_calendar_api()
    events_res = api.events.return_value

    events_res.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt-1",
                "summary": "Consulta Médica",
                "start": {"dateTime": "2026-11-24T09:00:00-03:00"},
                "end": {"dateTime": "2026-11-24T10:00:00-03:00"},
                "location": "Clínica Central",
                "hangoutLink": "https://meet.google.com/abc-defg-hij",
            }
        ]
    }
    events_res.insert.return_value.execute.return_value = {
        "id": "evt-2",
        "summary": "Reunião de Alinhamento",
        "start": {"dateTime": "2026-11-24T14:00:00-03:00"},
        "end": {"dateTime": "2026-11-24T15:00:00-03:00"},
        "hangoutLink": "https://meet.google.com/xyz-uvwx-rst",
        "htmlLink": "https://calendar.google.com/event?eid=evt-2",
        "attendees": [{"email": "guest@example.com"}],
    }

    service = GoogleCalendarService(service=api, timezone_name="America/Sao_Paulo")

    listed = await service.list_events(
        start_iso="2026-11-24T00:00:00",
        end_iso="2026-11-24T23:59:59",
        query="Consulta",
    )
    assert listed["status"] == "ok"
    assert listed["count"] == 1
    assert listed["events"][0]["summary"] == "Consulta Médica"
    assert listed["events"][0]["meet_link"] == "https://meet.google.com/abc-defg-hij"
    events_res.list.assert_called_once()
    list_kwargs = events_res.list.call_args.kwargs
    assert list_kwargs["calendarId"] == "primary"
    assert list_kwargs["q"] == "Consulta"

    created = await service.create_event(
        summary="Reunião de Alinhamento",
        start_iso="2026-11-24T14:00:00-03:00",
        end_iso="2026-11-24T15:00:00-03:00",
        attendees=["guest@example.com"],
        create_meet=True,
    )
    assert created["status"] == "ok"
    assert created["event_id"] == "evt-2"
    assert created["meet_link"] == "https://meet.google.com/xyz-uvwx-rst"
    assert created["hangoutLink"] == "https://meet.google.com/xyz-uvwx-rst"
    insert_kwargs = events_res.insert.call_args.kwargs
    assert insert_kwargs["calendarId"] == "primary"
    assert insert_kwargs["conferenceDataVersion"] == 1
    assert insert_kwargs["sendUpdates"] == "all"
    assert (
        insert_kwargs["body"]["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"]
        == "hangoutsMeet"
    )


async def test_google_calendar_update_and_delete_event() -> None:
    """Verify update_event patches fields and delete_event removes by event_id."""
    api = _make_mock_calendar_api()
    events_res = api.events.return_value
    events_res.patch.return_value.execute.return_value = {
        "id": "evt-10",
        "summary": "Culto Atualizado",
        "start": {"dateTime": "2026-11-25T19:30:00-03:00"},
        "end": {"dateTime": "2026-11-25T21:00:00-03:00"},
    }

    service = GoogleCalendarService(service=api, timezone_name="America/Sao_Paulo")

    empty_update = await service.update_event(event_id="evt-10")
    assert empty_update["status"] == "error"

    updated = await service.update_event(
        event_id="evt-10",
        summary="Culto Atualizado",
        start_iso="2026-11-25T19:30:00-03:00",
    )
    assert updated["status"] == "ok"
    assert updated["summary"] == "Culto Atualizado"
    events_res.patch.assert_called_once()

    deleted = await service.delete_event("evt-10")
    assert deleted == {"status": "ok", "event_id": "evt-10", "deleted": True}
    events_res.delete.assert_called_once_with(calendarId="primary", eventId="evt-10")


async def test_database_pending_confirmations_and_purge(tmp_path: Path) -> None:
    """Verify pending_confirmations CRUD, user isolation, and retention purge."""
    db_path = tmp_path / "confirm.db"
    db = Database(db_path)
    await db.init()

    conf_id = await db.create_pending_confirmation(
        user_id=100,
        tool_name="delete_calendar_event",
        args={"event_id": "evt-99"},
        summary_text="Excluir evento ID: evt-99",
    )
    assert conf_id > 0

    assert await db.get_pending_confirmation(conf_id, user_id=999) is None
    record = await db.get_pending_confirmation(conf_id, user_id=100)
    assert record is not None
    assert record.status == "pending"
    assert record.args["event_id"] == "evt-99"

    assert await db.resolve_pending_confirmation(conf_id, user_id=100, status="confirmed") is True
    assert await db.resolve_pending_confirmation(conf_id, user_id=100, status="cancelled") is False

    # Backdate created_at to verify purge_expired_data cleans pending_confirmations
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE pending_confirmations SET created_at = '2020-01-01T00:00:00+00:00'"
        )
        await conn.commit()

    purged = await db.purge_expired_data(retention_days=30)
    assert purged["pending_confirmations"] == 1


async def test_tool_executor_confirmation_policy_and_calendar_undo(tmp_path: Path) -> None:
    """Verify confirmation policy for external invites/deletes and direct personal undo."""
    db = Database(tmp_path / "exec.db")
    await db.init()

    calendar_service = AsyncMock(spec=GoogleCalendarService)
    calendar_service.create_event.return_value = {
        "status": "ok",
        "event_id": "evt-personal-1",
        "summary": "Dentista",
        "start": "2026-11-26T10:00:00-03:00",
        "end": "2026-11-26T11:00:00-03:00",
        "meet_link": "",
    }
    calendar_service.delete_event.return_value = {
        "status": "ok",
        "event_id": "evt-personal-1",
        "deleted": True,
    }

    executor = ToolExecutor(database=db, calendar_service=calendar_service)

    # 1. Event with external attendees must stage pending confirmation
    invite_res = await executor.execute(
        user_id=10,
        tool_name="create_calendar_event",
        arguments={
            "summary": "Sync Projeto",
            "start_iso": "2026-11-26T14:00:00-03:00",
            "end_iso": "2026-11-26T15:00:00-03:00",
            "attendees": ["peer@example.com"],
            "create_meet": True,
        },
    )
    assert invite_res["status"] == "confirmation_required"
    assert invite_res["pending_confirmation_id"] > 0
    calendar_service.create_event.assert_not_awaited()

    # 2. Delete event must always stage pending confirmation
    delete_res = await executor.execute(
        user_id=10,
        tool_name="delete_calendar_event",
        arguments={"event_id": "evt-old", "event_summary": "Evento Antigo"},
    )
    assert delete_res["status"] == "confirmation_required"
    assert delete_res["pending_confirmation_id"] > 0
    calendar_service.delete_event.assert_not_awaited()

    # 3. Personal event without attendees executes directly and records Undo
    personal_res = await executor.execute(
        user_id=10,
        tool_name="create_calendar_event",
        arguments={
            "summary": "Dentista",
            "start_iso": "2026-11-26T10:00:00-03:00",
            "end_iso": "2026-11-26T11:00:00-03:00",
        },
    )
    assert personal_res["status"] == "ok"
    assert personal_res["action_id"] > 0
    calendar_service.create_event.assert_awaited_once()

    undo_res = await executor.undo_action(user_id=10, action_id=personal_res["action_id"])
    assert undo_res["status"] == "ok"
    assert undo_res["target_system"] == "google_calendar"
    assert undo_res["event_id"] == "evt-personal-1"
    calendar_service.delete_event.assert_awaited_once_with("evt-personal-1")


async def test_orchestrator_sets_pending_confirmation_id(tmp_path: Path) -> None:
    """Verify AgentOrchestrator attaches pending_confirmation_id from tool execution."""
    db = Database(tmp_path / "orch.db")
    await db.init()

    calendar_service = AsyncMock(spec=GoogleCalendarService)
    executor = ToolExecutor(database=db, calendar_service=calendar_service)
    registry = ToolRegistry(enable_calendar_tools=True, enable_undo_tool=True)

    assert len(registry.definitions) == 8

    class _ConfirmProvider(BaseLLMProvider):
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
            assert tool_executor is not None
            tool_out = await tool_executor(
                "delete_calendar_event",
                {"event_id": "evt-55", "event_summary": "Reunião"},
            )
            assert tool_out["status"] == "confirmation_required"
            return AssistantStructuredReply(
                intent="clarification",
                summary="Confirme abaixo se deseja excluir o evento Reunião.",
            )

    orchestrator = AgentOrchestrator(
        provider=_ConfirmProvider(),
        database=db,
        timezone_name="America/Sao_Paulo",
        tool_registry=registry,
        tool_executor=executor,
    )

    reply = await orchestrator.process_message(user_id=77, text="Exclua a reunião")
    assert reply.pending_confirmation_id is not None
    assert reply.undo_action_id is None


async def test_bot_handlers_confirmation_buttons_and_callbacks(tmp_path: Path) -> None:
    """Verify inline [Confirmar]/[Cancelar] buttons and confirm:/cancel: callbacks."""
    db = Database(tmp_path / "bot_confirm.db")
    await db.init()

    calendar_service = AsyncMock(spec=GoogleCalendarService)
    calendar_service.create_event.return_value = {
        "status": "ok",
        "event_id": "evt-meet-9",
        "summary": "Reunião Cliente",
        "start": "2026-11-27T15:00:00-03:00",
        "end": "2026-11-27T16:00:00-03:00",
        "attendees": ["client@example.com"],
        "meet_link": "https://meet.google.com/aaa-bbbb-ccc",
        "hangoutLink": "https://meet.google.com/aaa-bbbb-ccc",
    }
    executor = ToolExecutor(database=db, calendar_service=calendar_service)

    conf_to_confirm = await db.create_pending_confirmation(
        user_id=555,
        tool_name="create_calendar_event",
        args={
            "summary": "Reunião Cliente",
            "start_iso": "2026-11-27T15:00:00-03:00",
            "end_iso": "2026-11-27T16:00:00-03:00",
            "attendees": ["client@example.com"],
            "create_meet": True,
        },
        summary_text="Criar evento 'Reunião Cliente'",
    )
    conf_to_cancel = await db.create_pending_confirmation(
        user_id=555,
        tool_name="delete_calendar_event",
        args={"event_id": "evt-keep"},
        summary_text="Excluir evento ID: evt-keep",
    )

    fake_reply = AssistantStructuredReply(
        intent="clarification",
        summary="Deseja confirmar o envio do convite?",
    )
    fake_reply.set_pending_confirmation_id(conf_to_confirm)

    orchestrator = MagicMock(spec=AgentOrchestrator)
    orchestrator.process_message = AsyncMock(return_value=fake_reply)

    handlers = BotHandlers(
        allowed_user_ids=[555],
        orchestrator=orchestrator,
        database=db,
        tool_executor=executor,
    )

    update = MagicMock()
    update.effective_user.id = 555
    update.effective_message.text = "Marque reunião com client@example.com com Meet"
    update.effective_message.chat.send_action = AsyncMock()
    update.effective_message.reply_text = AsyncMock()

    await handlers.text_message(update, MagicMock())
    reply_markup = update.effective_message.reply_text.call_args.kwargs["reply_markup"]
    buttons = reply_markup.inline_keyboard[0]
    assert buttons[0].text == "Confirmar"
    assert buttons[0].callback_data == f"confirm:{conf_to_confirm}"
    assert buttons[1].text == "Cancelar"
    assert buttons[1].callback_data == f"cancel:{conf_to_confirm}"

    # Trigger confirm callback
    cb_confirm = MagicMock()
    cb_confirm.effective_user.id = 555
    cb_confirm.callback_query.data = f"confirm:{conf_to_confirm}"
    cb_confirm.callback_query.answer = AsyncMock()
    cb_confirm.callback_query.edit_message_reply_markup = AsyncMock()
    cb_confirm.callback_query.message.reply_text = AsyncMock()

    await handlers.confirmation_callback(cb_confirm, MagicMock())
    calendar_service.create_event.assert_awaited_once()
    cb_confirm.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    confirm_text = cb_confirm.callback_query.message.reply_text.call_args.args[0]
    assert "Reunião Cliente" in confirm_text
    assert "https://meet.google.com/aaa-bbbb-ccc" in confirm_text

    # Trigger cancel callback
    cb_cancel = MagicMock()
    cb_cancel.effective_user.id = 555
    cb_cancel.callback_query.data = f"cancel:{conf_to_cancel}"
    cb_cancel.callback_query.answer = AsyncMock()
    cb_cancel.callback_query.edit_message_reply_markup = AsyncMock()
    cb_cancel.callback_query.message.reply_text = AsyncMock()

    await handlers.confirmation_callback(cb_cancel, MagicMock())
    calendar_service.delete_event.assert_not_awaited()
    cancel_text = cb_cancel.callback_query.message.reply_text.call_args.args[0]
    assert "cancelada" in cancel_text.lower()

    # Trigger undo callback for the created calendar event
    last_action = await db.get_last_undoable_action(user_id=555)
    assert last_action is not None
    cb_undo = MagicMock()
    cb_undo.effective_user.id = 555
    cb_undo.callback_query.data = f"undo:{last_action.id}"
    cb_undo.callback_query.answer = AsyncMock()
    cb_undo.callback_query.edit_message_reply_markup = AsyncMock()
    cb_undo.callback_query.message.reply_text = AsyncMock()

    await handlers.undo_callback(cb_undo, MagicMock())
    calendar_service.delete_event.assert_awaited_once_with("evt-meet-9")
    undo_text = cb_undo.callback_query.message.reply_text.call_args.args[0]
    assert "Evento removido da agenda com sucesso" in undo_text
