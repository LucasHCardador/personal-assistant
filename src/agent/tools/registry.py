"""Tool registry declaring available agent tools and their JSON schemas."""

from typing import Any

from pydantic import BaseModel

from src.agent.schemas import ToolDefinition
from src.agent.tools.schemas import (
    BudgetExpenseInput,
    BudgetSummaryQuery,
    CarExpenseInput,
    CreateCalendarEventInput,
    DeleteCalendarEventInput,
    FuelExpenseInput,
    ListCalendarEventsInput,
    MaintenanceStatusQuery,
    UndoActionInput,
    UpdateCalendarEventInput,
)


def _clean_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Generate a clean JSON schema dictionary for LLM tool declarations."""
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


class ToolRegistry:
    """Registry of active agent tools conditioned on configured integrations."""

    def __init__(
        self,
        *,
        enable_car_tools: bool = False,
        enable_budget_tools: bool = False,
        enable_calendar_tools: bool = False,
        enable_undo_tool: bool = False,
    ) -> None:
        self._definitions: list[ToolDefinition] = []

        if enable_car_tools:
            self._definitions.extend(
                [
                    ToolDefinition(
                        name="log_fuel_expense",
                        description=(
                            "Registra um abastecimento do veículo na planilha e calcula "
                            "preço/L, km rodados e consumo médio (km/L)."
                        ),
                        parameters_schema=_clean_json_schema(FuelExpenseInput),
                    ),
                    ToolDefinition(
                        name="log_car_expense",
                        description=(
                            "Registra manutenção realizada (atualizando o plano de manutenção) "
                            "ou despesa fixa/outra do veículo (IPVA, seguro, lavagem, multa)."
                        ),
                        parameters_schema=_clean_json_schema(CarExpenseInput),
                    ),
                    ToolDefinition(
                        name="get_car_maintenance_status",
                        description=(
                            "Consulta os itens do plano de manutenção do carro para verificar "
                            "quais estão próximos do vencimento ou vencidos."
                        ),
                        parameters_schema=_clean_json_schema(MaintenanceStatusQuery),
                    ),
                ]
            )

        if enable_budget_tools:
            self._definitions.extend(
                [
                    ToolDefinition(
                        name="log_budget_expense",
                        description=(
                            "Registra uma despesa ou receita na planilha de orçamento doméstico."
                        ),
                        parameters_schema=_clean_json_schema(BudgetExpenseInput),
                    ),
                    ToolDefinition(
                        name="get_budget_summary",
                        description=(
                            "Consulta o resumo de gastos do mês por categoria comparado às metas "
                            "do orçamento doméstico."
                        ),
                        parameters_schema=_clean_json_schema(BudgetSummaryQuery),
                    ),
                ]
            )

        if enable_calendar_tools:
            self._definitions.extend(
                [
                    ToolDefinition(
                        name="list_calendar_events",
                        description=(
                            "Lista compromissos e reuniões do Google Calendar em um intervalo "
                            "de datas."
                        ),
                        parameters_schema=_clean_json_schema(ListCalendarEventsInput),
                    ),
                    ToolDefinition(
                        name="create_calendar_event",
                        description=(
                            "Cria um compromisso ou reunião no Google Calendar, com suporte a "
                            "link do Google Meet e lista de convidados. Convites com participantes "
                            "exigem confirmação do usuário antes do envio."
                        ),
                        parameters_schema=_clean_json_schema(CreateCalendarEventInput),
                    ),
                    ToolDefinition(
                        name="update_calendar_event",
                        description=(
                            "Atualiza ou reagenda um compromisso existente no Google Calendar "
                            "a partir do seu event_id."
                        ),
                        parameters_schema=_clean_json_schema(UpdateCalendarEventInput),
                    ),
                    ToolDefinition(
                        name="delete_calendar_event",
                        description=(
                            "Solicita confirmação do usuário para excluir um compromisso do "
                            "Google Calendar a partir do seu event_id."
                        ),
                        parameters_schema=_clean_json_schema(DeleteCalendarEventInput),
                    ),
                ]
            )

        if enable_undo_tool:
            self._definitions.append(
                ToolDefinition(
                    name="undo_last_action",
                    description=(
                        "Desfaz o último lançamento em planilha ou evento criado na agenda "
                        "pelo usuário."
                    ),
                    parameters_schema=_clean_json_schema(UndoActionInput),
                )
            )

    @property
    def definitions(self) -> list[ToolDefinition]:
        """Return all registered tool definitions."""
        return list(self._definitions)

    @property
    def has_tools(self) -> bool:
        """Return True if at least one tool is registered."""
        return bool(self._definitions)
