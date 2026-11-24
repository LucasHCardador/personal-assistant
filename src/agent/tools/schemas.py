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
