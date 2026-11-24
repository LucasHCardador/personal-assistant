"""Tool executor validating inputs, running sheet operations, and recording undo history."""

import logging
from typing import Any

from pydantic import ValidationError

from src.agent.tools.schemas import (
    BudgetExpenseInput,
    BudgetSummaryQuery,
    CarExpenseInput,
    FuelExpenseInput,
    MaintenanceStatusQuery,
    UndoActionInput,
)
from src.integrations.google_sheets import GoogleSheetsService
from src.storage.database import Database

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes validated agent tools and persists reversible actions in SQLite."""

    def __init__(
        self,
        *,
        database: Database,
        sheets_service: GoogleSheetsService | None = None,
    ) -> None:
        self._db = database
        self._sheets = sheets_service

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
        except ValidationError as exc:
            logger.warning("Tool '%s' validation failed: %s", tool_name, exc)
            return {"status": "error", "error": f"Invalid arguments: {exc}"}
        except Exception as exc:
            logger.exception("Tool '%s' execution error: %s", tool_name, exc)
            return {"status": "error", "error": str(exc)}

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

    async def undo_action(
        self,
        *,
        user_id: int,
        action_id: int | None = None,
    ) -> dict[str, Any]:
        """Undo a previously recorded Google Sheets action for `user_id`."""
        record = await self._db.get_last_undoable_action(user_id=user_id, action_id=action_id)
        if record is None:
            return {
                "status": "not_found",
                "message": "Nenhuma ação recente disponível para desfazer.",
            }

        if record.target_system != "google_sheets":
            return {
                "status": "error",
                "error": f"Unsupported target_system for undo: {record.target_system}",
            }

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
            "undone_action_id": record.id,
            "action_type": record.action_type,
            "worksheet": worksheet_name,
            "record_id": record.external_id,
            "row_deleted_from_sheet": deleted,
        }
