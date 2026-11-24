"""Strict Pydantic input schemas for agent tools."""

from typing import Literal

from pydantic import BaseModel, Field


class FuelExpenseInput(BaseModel):
    """Input schema for logging a vehicle fuel fill-up."""

    date: str = Field(description="Data do abastecimento no formato YYYY-MM-DD.")
    current_km: int = Field(gt=0, description="Quilometragem atual do painel (km).")
    fuel_type: str = Field(
        default="Gasolina",
        description="Tipo de combustível (ex: Gasolina, Etanol, Diesel, GNV).",
    )
    liters: float = Field(gt=0, description="Quantidade abastecida em litros.")
    total_value: float = Field(gt=0, description="Valor total pago em reais (R$).")
    station: str = Field(default="", description="Nome do posto de combustível (opcional).")
    notes: str = Field(default="", description="Observações adicionais (opcional).")


class CarExpenseInput(BaseModel):
    """Input schema for logging vehicle maintenance or fixed/other expenses."""

    expense_kind: Literal["maintenance", "fixed_or_other"] = Field(
        description=(
            "'maintenance' para revisões, trocas de óleo/peças e serviços; "
            "'fixed_or_other' para IPVA, seguro, lavagem, estacionamento ou multa."
        )
    )
    date: str = Field(description="Data da despesa no formato YYYY-MM-DD.")
    description: str = Field(min_length=1, description="Descrição do serviço ou despesa.")
    value: float = Field(gt=0, description="Valor total em reais (R$).")
    km: int | None = Field(default=None, gt=0, description="Quilometragem no momento (opcional).")
    workshop: str = Field(default="", description="Nome da oficina ou prestador (opcional).")
    category: str = Field(
        default="Outros",
        description=(
            "Categoria para despesas fixas "
            "(IPVA, Seguro, Lavagem, Estacionamento, Multa, Outros)."
        ),
    )
    next_km: int | None = Field(
        default=None, gt=0, description="Próxima quilometragem recomendada (opcional)."
    )
    next_date: str | None = Field(
        default=None, description="Próxima data recomendada no formato YYYY-MM-DD (opcional)."
    )
    notes: str = Field(default="", description="Notas adicionais (opcional).")


class MaintenanceStatusQuery(BaseModel):
    """Input schema for querying vehicle maintenance plan status."""

    current_km: int | None = Field(
        default=None,
        gt=0,
        description="Quilometragem atual opcional para calcular itens próximos do vencimento.",
    )


class CarPerformanceQuery(BaseModel):
    """Input schema for querying detailed vehicle fuel consumption and cost evolution."""

    last_n_refills: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Quantidade de abastecimentos recentes para detalhar na evolução.",
    )


class BudgetExpenseInput(BaseModel):
    """Input schema for logging a household budget expense or income."""

    date: str = Field(description="Data do lançamento no formato YYYY-MM-DD.")
    entry_type: Literal["Despesa", "Receita"] = Field(
        default="Despesa",
        description="Tipo do lançamento: 'Despesa' ou 'Receita'.",
    )
    category: str = Field(
        description="Categoria (Mercado, Saúde, Igreja, Casa, Lazer, Transporte, Outros)."
    )
    description: str = Field(min_length=1, description="Descrição curta do gasto ou receita.")
    value: float = Field(gt=0, description="Valor em reais (R$).")
    subcategory: str = Field(default="", description="Subcategoria opcional.")
    payment_method: str = Field(
        default="",
        description="Forma de pagamento (ex: Débito, Crédito, Pix, Dinheiro).",
    )


class BudgetSummaryQuery(BaseModel):
    """Input schema for querying monthly household budget summary."""

    year_month: str | None = Field(
        default=None,
        description="Mês de referência no formato YYYY-MM (padrão: mês atual).",
    )


class UndoActionInput(BaseModel):
    """Input schema for undoing the last recorded action."""

    action_id: int | None = Field(
        default=None,
        description="ID específico da ação a desfazer; se omitido, desfaz a última ação.",
    )


class ListCalendarEventsInput(BaseModel):
    """Input schema for listing events from Google Calendar."""

    start_iso: str = Field(
        description="Início do intervalo no formato ISO 8601 (ex: 2026-11-24T00:00:00-03:00)."
    )
    end_iso: str = Field(
        description="Fim do intervalo no formato ISO 8601 (ex: 2026-11-24T23:59:59-03:00)."
    )
    query: str | None = Field(
        default=None,
        description="Termo opcional para filtrar eventos por título ou descrição.",
    )


class CreateCalendarEventInput(BaseModel):
    """Input schema for creating a Google Calendar event."""

    summary: str = Field(min_length=1, description="Título do compromisso ou reunião.")
    start_iso: str = Field(
        description="Data e hora de início no formato ISO 8601 (ex: 2026-11-24T14:00:00-03:00)."
    )
    end_iso: str = Field(
        description="Data e hora de término no formato ISO 8601 (ex: 2026-11-24T15:00:00-03:00)."
    )
    description: str | None = Field(
        default=None,
        description="Descrição ou pauta do evento (opcional).",
    )
    location: str | None = Field(
        default=None,
        description="Local físico ou endereço (opcional).",
    )
    attendees: list[str] = Field(
        default_factory=list,
        description="Lista de e-mails de participantes convidados (opcional).",
    )
    create_meet: bool = Field(
        default=False,
        description="Se true, gera automaticamente um link de videoconferência do Google Meet.",
    )
    recurrence_rrule: str | None = Field(
        default=None,
        description=(
            "Regra opcional de recorrência RFC 5545 RRULE "
            "(ex: 'RRULE:FREQ=WEEKLY;INTERVAL=2' para quinzenal, "
            "'RRULE:FREQ=WEEKLY' para semanal, 'RRULE:FREQ=MONTHLY' para mensal)."
        ),
    )


class UpdateCalendarEventInput(BaseModel):
    """Input schema for updating an existing Google Calendar event."""

    event_id: str = Field(min_length=1, description="ID do evento no Google Calendar.")
    summary: str | None = Field(default=None, description="Novo título do evento (opcional).")
    start_iso: str | None = Field(
        default=None, description="Nova data e hora de início ISO 8601 (opcional)."
    )
    end_iso: str | None = Field(
        default=None, description="Nova data e hora de término ISO 8601 (opcional)."
    )
    description: str | None = Field(default=None, description="Nova descrição (opcional).")
    location: str | None = Field(default=None, description="Novo local (opcional).")


class DeleteCalendarEventInput(BaseModel):
    """Input schema for deleting a Google Calendar event (always requires confirmation)."""

    event_id: str = Field(min_length=1, description="ID do evento no Google Calendar.")
    event_summary: str | None = Field(
        default=None,
        description="Título do evento para exibir no pedido de confirmação (opcional).",
    )


class CreateReminderInput(BaseModel):
    """Input schema for creating a one-shot or recurring reminder."""

    title: str = Field(min_length=1, description="Texto ou título do lembrete.")
    trigger_at_iso: str = Field(
        description="Data e hora do disparo no formato ISO 8601 (ex: 2026-11-24T09:00:00-03:00)."
    )
    recurrence: Literal["once", "daily", "weekly", "monthly"] = Field(
        default="once",
        description="Frequência do lembrete: 'once', 'daily', 'weekly' ou 'monthly'.",
    )


class ListRemindersInput(BaseModel):
    """Input schema for listing user reminders."""

    status: Literal["pending", "sent", "cancelled", "all"] = Field(
        default="pending",
        description="Filtro de status dos lembretes: 'pending', 'sent', 'cancelled' ou 'all'.",
    )


class CancelReminderInput(BaseModel):
    """Input schema for cancelling a pending reminder."""

    reminder_id: int = Field(gt=0, description="ID numérico do lembrete a cancelar.")
