"""Unit tests for Google Sheets service, tool calling, and undo flow."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

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
from src.integrations.google_sheets import GoogleSheetsService
from src.storage.database import Database


def _make_mock_gspread_client(worksheets: dict[str, MagicMock]) -> MagicMock:
    """Build a mock gspread.Client routing worksheet lookups by name."""
    spreadsheet = MagicMock()
    spreadsheet.worksheet.side_effect = lambda name: worksheets[name]
    client = MagicMock()
    client.open_by_key.return_value = spreadsheet
    return client


async def test_google_sheets_fuel_consumption_calculation() -> None:
    """Verify log_fuel_expense computes price/L, km driven, and km/L consumption."""
    fuel_ws = MagicMock()
    fuel_ws.get_all_records.return_value = [
        {"ID": "prev1", "Km Atual": 45000},
    ]
    client = _make_mock_gspread_client({"Abastecimentos": fuel_ws})

    service = GoogleSheetsService(
        client=client,
        car_spreadsheet_id="car-sheet-id",
        timezone_name="America/Sao_Paulo",
    )

    result = await service.log_fuel_expense(
        date="2026-11-23",
        current_km=45420,
        fuel_type="Gasolina",
        liters=35.0,
        total_value=210.0,
        station="Posto Central",
    )

    assert result["status"] == "ok"
    assert result["price_per_liter"] == 6.0
    assert result["km_driven"] == 420
    assert result["consumption_km_l"] == 12.0
    fuel_ws.append_row.assert_called_once()
    appended_row = fuel_ws.append_row.call_args.args[0]
    assert appended_row[0] == result["record_id"]
    assert appended_row[8] == 420
    assert appended_row[9] == 12.0


async def test_google_sheets_maintenance_updates_plan_and_status() -> None:
    """Verify maintenance logging updates Plano_Manutencao and status checks detect due items."""
    maint_ws = MagicMock()
    plan_ws = MagicMock()
    plan_ws.get_all_records.return_value = [
        {
            "Item": "Óleo e Filtro",
            "Intervalo Km": 10000,
            "Intervalo Meses": 12,
            "Último Km": 35000,
            "Última Data": "2025-11-01",
            "Próximo Km": 45000,
            "Próxima Data": "2026-11-01",
            "Status": "Em dia",
        }
    ]
    fuel_ws = MagicMock()
    fuel_ws.get_all_records.return_value = [{"Km Atual": 45500}]

    client = _make_mock_gspread_client(
        {
            "Manutencoes_Realizadas": maint_ws,
            "Plano_Manutencao": plan_ws,
            "Abastecimentos": fuel_ws,
        }
    )

    service = GoogleSheetsService(
        client=client,
        car_spreadsheet_id="car-sheet-id",
        timezone_name="America/Sao_Paulo",
    )

    status_before = await service.get_car_maintenance_status()
    assert status_before["current_km"] == 45500
    assert "Vencido" in status_before["items"][0]["status"]

    log_result = await service.log_car_expense(
        expense_kind="maintenance",
        date="2026-11-23",
        description="Troca de Óleo e Filtro",
        value=320.0,
        km=45500,
        workshop="Oficina Silva",
    )
    assert log_result["status"] == "ok"
    assert log_result["plan_updated"] is True
    maint_ws.append_row.assert_called_once()
    plan_ws.update.assert_called_once()


async def test_google_sheets_budget_summary_and_delete_row() -> None:
    """Verify budget summary aggregation and row deletion by ID."""
    entries_ws = MagicMock()
    entries_ws.get_all_records.return_value = [
        {
            "ID": "b1",
            "Data": "2026-11-05",
            "Tipo": "Despesa",
            "Categoria": "Mercado",
            "Valor": 450.0,
        },
        {
            "ID": "b2",
            "Data": "2026-11-12",
            "Tipo": "Despesa",
            "Categoria": "Mercado",
            "Valor": 400.0,
        },
        {
            "ID": "b3",
            "Data": "2026-10-20",
            "Tipo": "Despesa",
            "Categoria": "Mercado",
            "Valor": 999.0,
        },
        {
            "ID": "b4",
            "Data": "2026-11-01",
            "Tipo": "Receita",
            "Categoria": "Outros",
            "Valor": 5000.0,
        },
    ]
    entries_ws.col_values.return_value = ["ID", "b1", "b2", "b3", "b4"]
    goals_ws = MagicMock()
    goals_ws.get_all_records.return_value = [
        {"Categoria": "Mercado", "Limite Mensal": 1000.0, "Alerta (%)": 80},
    ]

    client = _make_mock_gspread_client(
        {
            "Lancamentos": entries_ws,
            "Metas_Orcamento": goals_ws,
        }
    )
    service = GoogleSheetsService(
        client=client,
        budget_spreadsheet_id="budget-sheet-id",
        timezone_name="America/Sao_Paulo",
    )

    summary = await service.get_budget_summary(year_month="2026-11")
    assert summary["total_expenses"] == 850.0
    assert summary["total_income"] == 5000.0
    mercado = next(c for c in summary["categories"] if c["category"] == "Mercado")
    assert mercado["spent"] == 850.0
    assert mercado["percent_used"] == 85.0
    assert mercado["near_or_over_limit"] is True

    deleted = await service.delete_row_by_id(
        spreadsheet_key="budget",
        worksheet_name="Lancamentos",
        record_id="b2",
    )
    assert deleted is True
    entries_ws.delete_rows.assert_called_once_with(3)


async def test_database_action_history_and_executor_undo(tmp_path: Path) -> None:
    """Verify action_history recording, retrieval, and ToolExecutor undo flow."""
    db = Database(tmp_path / "undo.db")
    await db.init()

    entries_ws = MagicMock()
    entries_ws.col_values.return_value = ["ID"]
    client = _make_mock_gspread_client({"Lancamentos": entries_ws})

    service = GoogleSheetsService(
        client=client,
        budget_spreadsheet_id="budget-sheet-id",
    )
    executor = ToolExecutor(database=db, sheets_service=service)

    exec_result = await executor.execute(
        user_id=42,
        tool_name="log_budget_expense",
        arguments={
            "date": "2026-11-23",
            "entry_type": "Despesa",
            "category": "Mercado",
            "description": "Compras da semana",
            "value": 180.5,
            "payment_method": "Débito",
        },
    )
    assert exec_result["status"] == "ok"
    action_id = exec_result["action_id"]
    record_id = exec_result["record_id"]

    entries_ws.col_values.return_value = ["ID", record_id]
    last_action = await db.get_last_undoable_action(user_id=42)
    assert last_action is not None
    assert last_action.id == action_id
    assert last_action.external_id == record_id

    undo_result = await executor.execute(
        user_id=42,
        tool_name="undo_last_action",
        arguments={},
    )
    assert undo_result["status"] == "ok"
    assert undo_result["row_deleted_from_sheet"] is True
    entries_ws.delete_rows.assert_called_once_with(2)

    assert await db.get_last_undoable_action(user_id=42) is None


async def test_tool_executor_rejects_invalid_arguments(tmp_path: Path) -> None:
    """Verify Pydantic validation errors return structured error payloads."""
    db = Database(tmp_path / "val.db")
    await db.init()
    executor = ToolExecutor(database=db, sheets_service=MagicMock())

    result = await executor.execute(
        user_id=1,
        tool_name="log_fuel_expense",
        arguments={"date": "2026-11-23", "current_km": -10, "liters": 0, "total_value": 100},
    )
    assert result["status"] == "error"
    assert "Invalid arguments" in result["error"]


class _ToolCallingFakeProvider(BaseLLMProvider):
    """Fake LLM provider that invokes a tool before returning AssistantStructuredReply."""

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
        assert tools is not None and len(tools) > 0
        assert tool_executor is not None
        tool_res = await tool_executor(
            "log_budget_expense",
            {
                "date": "2026-11-23",
                "entry_type": "Despesa",
                "category": "Mercado",
                "description": "Padaria",
                "value": 35.0,
            },
        )
        assert tool_res["status"] == "ok"
        return AssistantStructuredReply(
            intent="action_result",
            summary="Gasto de R$ 35,00 registrado em Mercado.",
            details=["Padaria — R$ 35,00"],
        )


async def test_orchestrator_tool_loop_sets_undo_action_id(tmp_path: Path) -> None:
    """Verify AgentOrchestrator runs tool loop and attaches undo_action_id."""
    db = Database(tmp_path / "orch_tools.db")
    await db.init()

    entries_ws = MagicMock()
    client = _make_mock_gspread_client({"Lancamentos": entries_ws})
    service = GoogleSheetsService(client=client, budget_spreadsheet_id="budget-id")
    registry = ToolRegistry(enable_budget_tools=True, enable_undo_tool=True)
    executor = ToolExecutor(database=db, sheets_service=service)

    orchestrator = AgentOrchestrator(
        provider=_ToolCallingFakeProvider(),
        database=db,
        timezone_name="America/Sao_Paulo",
        tool_registry=registry,
        tool_executor=executor,
    )

    reply = await orchestrator.process_message(user_id=77, text="Gastei 35 na padaria")
    assert reply.intent == "action_result"
    assert reply.undo_action_id is not None


async def test_bot_handler_attaches_undo_button_and_handles_callback(tmp_path: Path) -> None:
    """Verify BotHandlers sends inline 'Desfazer' button and processes callback."""
    db = Database(tmp_path / "bot_undo.db")
    await db.init()

    entries_ws = MagicMock()
    client = _make_mock_gspread_client({"Lancamentos": entries_ws})
    service = GoogleSheetsService(client=client, budget_spreadsheet_id="budget-id")
    registry = ToolRegistry(enable_budget_tools=True, enable_undo_tool=True)
    executor = ToolExecutor(database=db, sheets_service=service)

    orchestrator = AgentOrchestrator(
        provider=_ToolCallingFakeProvider(),
        database=db,
        timezone_name="America/Sao_Paulo",
        tool_registry=registry,
        tool_executor=executor,
    )
    handlers = BotHandlers(
        allowed_user_ids=[77],
        orchestrator=orchestrator,
        database=db,
        tool_executor=executor,
    )

    message = MagicMock()
    message.text = "Gastei 35 na padaria"
    message.chat.send_action = AsyncMock()
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 77
    update.effective_message = message

    await handlers.text_message(update, MagicMock())
    message.reply_text.assert_awaited_once()
    reply_kwargs: dict[str, Any] = message.reply_text.call_args.kwargs
    markup = reply_kwargs["reply_markup"]
    assert markup is not None
    callback_data = markup.inline_keyboard[0][0].callback_data
    assert callback_data.startswith("undo:")

    # Simulate user clicking "Desfazer"
    saved_action = await db.get_last_undoable_action(user_id=77)
    assert saved_action is not None
    entries_ws.col_values.return_value = ["ID", saved_action.external_id]

    cb_message = MagicMock()
    cb_message.reply_text = AsyncMock()
    query = MagicMock()
    query.data = callback_data
    query.message = cb_message
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()

    cb_update = MagicMock()
    cb_update.effective_user.id = 77
    cb_update.callback_query = query

    await handlers.undo_callback(cb_update, MagicMock())
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    cb_message.reply_text.assert_awaited_once()
    assert "desfeito com sucesso" in cb_message.reply_text.call_args.args[0].lower()
