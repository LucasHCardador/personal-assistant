"""Tool executor validating inputs, running integrations, and managing undo/confirmations."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from src.agent.tools.schemas import (
    BudgetExpenseInput,
    BudgetSummaryQuery,
    CancelReminderInput,
    CarExpenseInput,
    CreateCalendarEventInput,
    CreateReminderInput,
    DeleteCalendarEventInput,
    FuelExpenseInput,
    ListCalendarEventsInput,
    ListRemindersInput,
    MaintenanceStatusQuery,
    UndoActionInput,
    UpdateCalendarEventInput,
)
from src.integrations.google_calendar import GoogleCalendarService
from src.integrations.google_sheets import GoogleSheetsService
from src.storage.database import Database

logger = logging.getLogger(__name__)

_CALENDAR_TOOLS = frozenset(
    {
        "list_calendar_events",
        "create_calendar_event",
        "update_calendar_event",
        "delete_calendar_event",
    }
)

_REMINDER_TOOLS = frozenset(
    {
        "create_reminder",
        "list_reminders",
        "cancel_reminder",
    }
)


class ToolExecutor:
    """Executes validated agent tools and persists reversible/confirmable actions in SQLite."""

    def __init__(
        self,
        *,
        database: Database,
        sheets_service: GoogleSheetsService | None = None,
        calendar_service: GoogleCalendarService | None = None,
        timezone_name: str = "America/Sao_Paulo",
    ) -> None:
        self._db = database
        self._sheets = sheets_service
        self._calendar = calendar_service
        self._timezone = ZoneInfo(timezone_name)

    async def execute(
        self,
        *,
        user_id: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate arguments and dispatch the requested tool."""
        try:
            if tool_name == "undo_last_action":
                parsed_undo = UndoActionInput.model_validate(arguments)
                return await self.undo_action(user_id=user_id, action_id=parsed_undo.action_id)

            if tool_name in _REMINDER_TOOLS:
                return await self._execute_reminder_tool(
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=arguments,
                )

            if tool_name in _CALENDAR_TOOLS:
                return await self._execute_calendar_tool(
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=arguments,
                )

            return await self._execute_sheets_tool(
                user_id=user_id,
                tool_name=tool_name,
                arguments=arguments,
            )
        except ValidationError as exc:
            logger.warning("Tool '%s' validation failed: %s", tool_name, exc)
            return {"status": "error", "error": f"Invalid arguments: {exc}"}
        except Exception as exc:
            logger.exception("Tool '%s' execution error: %s", tool_name, exc)
            return {"status": "error", "error": str(exc)}

    async def _execute_sheets_tool(
        self,
        *,
        user_id: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Google Sheets tools with undo recording for writes."""
        if self._sheets is None:
            return {"status": "error", "error": "Google Sheets integration is not configured."}

        if tool_name == "log_fuel_expense":
            parsed_fuel = FuelExpenseInput.model_validate(arguments)
            result = await self._sheets.log_fuel_expense(
                date=parsed_fuel.date,
                current_km=parsed_fuel.current_km,
                fuel_type=parsed_fuel.fuel_type,
                liters=parsed_fuel.liters,
                total_value=parsed_fuel.total_value,
                station=parsed_fuel.station,
                notes=parsed_fuel.notes,
            )
            return await self._record_sheet_action(user_id, tool_name, result)

        if tool_name == "log_car_expense":
            parsed_car = CarExpenseInput.model_validate(arguments)
            result = await self._sheets.log_car_expense(
                expense_kind=parsed_car.expense_kind,
                date=parsed_car.date,
                description=parsed_car.description,
                value=parsed_car.value,
                km=parsed_car.km,
                workshop=parsed_car.workshop,
                category=parsed_car.category,
                next_km=parsed_car.next_km,
                next_date=parsed_car.next_date,
                notes=parsed_car.notes,
            )
            return await self._record_sheet_action(user_id, tool_name, result)

        if tool_name == "get_car_maintenance_status":
            parsed_status = MaintenanceStatusQuery.model_validate(arguments)
            return await self._sheets.get_car_maintenance_status(
                current_km=parsed_status.current_km
            )

        if tool_name == "log_budget_expense":
            parsed_budget = BudgetExpenseInput.model_validate(arguments)
            result = await self._sheets.log_budget_expense(
                date=parsed_budget.date,
                entry_type=parsed_budget.entry_type,
                category=parsed_budget.category,
                description=parsed_budget.description,
                value=parsed_budget.value,
                subcategory=parsed_budget.subcategory,
                payment_method=parsed_budget.payment_method,
            )
            return await self._record_sheet_action(user_id, tool_name, result)

        if tool_name == "get_budget_summary":
            parsed_summary = BudgetSummaryQuery.model_validate(arguments)
            return await self._sheets.get_budget_summary(year_month=parsed_summary.year_month)

        return {"status": "error", "error": f"Unknown tool: {tool_name}"}

    async def _execute_calendar_tool(
        self,
        *,
        user_id: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Google Calendar tools enforcing inline confirmation policy."""
        if self._calendar is None:
            return {"status": "error", "error": "Google Calendar integration is not configured."}

        if tool_name == "list_calendar_events":
            parsed_list = ListCalendarEventsInput.model_validate(arguments)
            return await self._calendar.list_events(
                start_iso=parsed_list.start_iso,
                end_iso=parsed_list.end_iso,
                query=parsed_list.query,
            )

        if tool_name == "create_calendar_event":
            parsed_create = CreateCalendarEventInput.model_validate(arguments)
            clean_attendees = [e.strip() for e in parsed_create.attendees if e.strip()]
            if clean_attendees:
                summary_text = (
                    f"Criar evento '{parsed_create.summary}' "
                    f"({parsed_create.start_iso} -> {parsed_create.end_iso}) "
                    f"com convidados: {', '.join(clean_attendees)}"
                )
                confirmation_id = await self._db.create_pending_confirmation(
                    user_id=user_id,
                    tool_name="create_calendar_event",
                    args={**parsed_create.model_dump(), "attendees": clean_attendees},
                    summary_text=summary_text,
                )
                return {
                    "status": "confirmation_required",
                    "pending_confirmation_id": confirmation_id,
                    "summary_text": summary_text,
                    "message": (
                        "Convite com participantes externos aguarda confirmação via botão inline."
                    ),
                }

            result = await self._calendar.create_event(
                summary=parsed_create.summary,
                start_iso=parsed_create.start_iso,
                end_iso=parsed_create.end_iso,
                description=parsed_create.description,
                location=parsed_create.location,
                attendees=None,
                create_meet=parsed_create.create_meet,
            )
            return await self._record_calendar_action(user_id, tool_name, result)

        if tool_name == "update_calendar_event":
            parsed_update = UpdateCalendarEventInput.model_validate(arguments)
            return await self._calendar.update_event(
                event_id=parsed_update.event_id,
                summary=parsed_update.summary,
                start_iso=parsed_update.start_iso,
                end_iso=parsed_update.end_iso,
                description=parsed_update.description,
                location=parsed_update.location,
            )

        if tool_name == "delete_calendar_event":
            parsed_delete = DeleteCalendarEventInput.model_validate(arguments)
            summary_label = (
                f"'{parsed_delete.event_summary}' (ID: {parsed_delete.event_id})"
                if parsed_delete.event_summary
                else f"ID: {parsed_delete.event_id}"
            )
            summary_text = f"Excluir evento {summary_label}"
            confirmation_id = await self._db.create_pending_confirmation(
                user_id=user_id,
                tool_name="delete_calendar_event",
                args=parsed_delete.model_dump(),
                summary_text=summary_text,
            )
            return {
                "status": "confirmation_required",
                "pending_confirmation_id": confirmation_id,
                "summary_text": summary_text,
                "message": "Exclusão de evento aguarda confirmação via botão inline.",
            }

        return {"status": "error", "error": f"Unknown calendar tool: {tool_name}"}

    async def _execute_reminder_tool(
        self,
        *,
        user_id: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute local SQLite reminder tools."""
        if tool_name == "create_reminder":
            parsed = CreateReminderInput.model_validate(arguments)
            parsed_dt = datetime.fromisoformat(parsed.trigger_at_iso.replace("Z", "+00:00"))
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=self._timezone)
            normalized_iso = parsed_dt.isoformat()
            recurrence_db = None if parsed.recurrence == "once" else parsed.recurrence
            reminder_id = await self._db.create_reminder(
                user_id=user_id,
                title=parsed.title,
                trigger_at=normalized_iso,
                recurrence=recurrence_db,
            )
            return {
                "status": "ok",
                "reminder_id": reminder_id,
                "title": parsed.title,
                "trigger_at": normalized_iso,
                "recurrence": parsed.recurrence,
            }

        if tool_name == "list_reminders":
            parsed_list = ListRemindersInput.model_validate(arguments)
            status_filter = None if parsed_list.status == "all" else parsed_list.status
            records = await self._db.list_reminders(user_id=user_id, status=status_filter)
            return {
                "status": "ok",
                "count": len(records),
                "reminders": [
                    {
                        "id": record.id,
                        "title": record.title,
                        "trigger_at": record.trigger_at,
                        "recurrence": record.recurrence or "once",
                        "status": record.status,
                    }
                    for record in records
                ],
            }

        if tool_name == "cancel_reminder":
            parsed_cancel = CancelReminderInput.model_validate(arguments)
            cancelled = await self._db.cancel_reminder(
                reminder_id=parsed_cancel.reminder_id,
                user_id=user_id,
            )
            if not cancelled:
                return {
                    "status": "not_found",
                    "message": "Lembrete não encontrado ou já finalizado.",
                }
            return {
                "status": "ok",
                "reminder_id": parsed_cancel.reminder_id,
                "message": "Lembrete cancelado.",
            }

        return {"status": "error", "error": f"Unknown reminder tool: {tool_name}"}

    async def execute_pending_confirmation(
        self,
        *,
        user_id: int,
        confirmation_id: int,
        approve: bool,
    ) -> dict[str, Any]:
        """Approve or cancel a previously staged `pending_confirmations` action."""
        record = await self._db.get_pending_confirmation(confirmation_id, user_id)
        if record is None:
            return {
                "status": "not_found",
                "message": "Solicitação de confirmação não encontrada.",
            }

        if record.status != "pending":
            return {
                "status": "already_resolved",
                "current_status": record.status,
                "message": "Esta confirmação já foi processada.",
            }

        if not approve:
            resolved = await self._db.resolve_pending_confirmation(
                confirmation_id, user_id, "cancelled"
            )
            if not resolved:
                return {
                    "status": "already_resolved",
                    "message": "Esta confirmação já foi processada.",
                }
            return {
                "status": "cancelled",
                "confirmation_id": confirmation_id,
                "tool_name": record.tool_name,
                "summary_text": record.summary_text,
            }

        if self._calendar is None:
            return {"status": "error", "error": "Google Calendar integration is not configured."}

        if record.tool_name == "create_calendar_event":
            parsed_create = CreateCalendarEventInput.model_validate(record.args)
            result = await self._calendar.create_event(
                summary=parsed_create.summary,
                start_iso=parsed_create.start_iso,
                end_iso=parsed_create.end_iso,
                description=parsed_create.description,
                location=parsed_create.location,
                attendees=parsed_create.attendees or None,
                create_meet=parsed_create.create_meet,
            )
            result = await self._record_calendar_action(
                user_id, "create_calendar_event", result
            )
        elif record.tool_name == "delete_calendar_event":
            parsed_delete = DeleteCalendarEventInput.model_validate(record.args)
            result = await self._calendar.delete_event(parsed_delete.event_id)
        else:
            return {"status": "error", "error": f"Unsupported pending tool: {record.tool_name}"}

        await self._db.resolve_pending_confirmation(confirmation_id, user_id, "confirmed")
        return {
            **result,
            "confirmation_id": confirmation_id,
            "tool_name": record.tool_name,
        }

    async def _record_sheet_action(
        self,
        user_id: int,
        action_type: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist undo metadata for a successful Google Sheets write."""
        record_id = str(result.get("record_id", ""))
        if not record_id:
            return result

        action_id = await self._db.record_action(
            user_id=user_id,
            action_type=action_type,
            target_system="google_sheets",
            external_id=record_id,
            payload={
                "spreadsheet": result.get("spreadsheet"),
                "worksheet": result.get("worksheet"),
                "record_id": record_id,
            },
        )
        return {**result, "action_id": action_id}

    async def _record_calendar_action(
        self,
        user_id: int,
        action_type: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist undo metadata for a newly created Google Calendar event."""
        event_id = str(result.get("event_id", ""))
        if not event_id:
            return result

        action_id = await self._db.record_action(
            user_id=user_id,
            action_type=action_type,
            target_system="google_calendar",
            external_id=event_id,
            payload={
                "event_id": event_id,
                "summary": result.get("summary", ""),
            },
        )
        return {**result, "action_id": action_id}

    async def undo_action(
        self,
        *,
        user_id: int,
        action_id: int | None = None,
    ) -> dict[str, Any]:
        """Undo a previously recorded Google Sheets or Google Calendar action."""
        record = await self._db.get_last_undoable_action(user_id=user_id, action_id=action_id)
        if record is None:
            return {
                "status": "not_found",
                "message": "Nenhuma ação recente disponível para desfazer.",
            }

        if record.target_system == "google_sheets":
            if self._sheets is None:
                return {"status": "error", "error": "Google Sheets integration is not configured."}

            spreadsheet_key = record.payload.get("spreadsheet")
            worksheet_name = record.payload.get("worksheet")
            if spreadsheet_key not in ("car", "budget") or not worksheet_name:
                return {"status": "error", "error": "Invalid action_history payload."}

            deleted = await self._sheets.delete_row_by_id(
                spreadsheet_key=spreadsheet_key,
                worksheet_name=str(worksheet_name),
                record_id=record.external_id,
            )
            await self._db.mark_action_undone(action_id=record.id, user_id=user_id)
            return {
                "status": "ok",
                "target_system": "google_sheets",
                "undone_action_id": record.id,
                "action_type": record.action_type,
                "worksheet": worksheet_name,
                "record_id": record.external_id,
                "row_deleted_from_sheet": deleted,
            }

        if record.target_system == "google_calendar":
            if self._calendar is None:
                return {
                    "status": "error",
                    "error": "Google Calendar integration is not configured.",
                }

            await self._calendar.delete_event(record.external_id)
            await self._db.mark_action_undone(action_id=record.id, user_id=user_id)
            return {
                "status": "ok",
                "target_system": "google_calendar",
                "undone_action_id": record.id,
                "action_type": record.action_type,
                "event_id": record.external_id,
                "summary": record.payload.get("summary", ""),
            }

        return {
            "status": "error",
            "error": f"Unsupported target_system for undo: {record.target_system}",
        }
