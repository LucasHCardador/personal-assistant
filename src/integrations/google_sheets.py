"""Google Sheets client and domain operations for vehicle and budget tracking."""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import gspread

CAR_SPREADSHEET_TITLE = "Assistente - Controle Veicular"
BUDGET_SPREADSHEET_TITLE = "Assistente - Orçamento Doméstico"

CAR_WORKSHEET_HEADERS: dict[str, list[str]] = {
    "Abastecimentos": [
        "ID",
        "Data",
        "Km Atual",
        "Combustível",
        "Litros",
        "Valor Total",
        "Preço/L",
        "Posto",
        "Km Rodados",
        "Consumo (km/L)",
        "Observações",
    ],
    "Manutencoes_Realizadas": [
        "ID",
        "Data",
        "Km",
        "Serviço/Item",
        "Oficina",
        "Valor",
        "Próxima Troca (Km)",
        "Próxima Troca (Data)",
        "Notas",
    ],
    "Plano_Manutencao": [
        "Item",
        "Intervalo Km",
        "Intervalo Meses",
        "Último Km",
        "Última Data",
        "Próximo Km",
        "Próxima Data",
        "Status",
    ],
    "Despesas_Fixas_Outros": [
        "ID",
        "Data",
        "Categoria",
        "Descrição",
        "Valor",
    ],
}

BUDGET_WORKSHEET_HEADERS: dict[str, list[str]] = {
    "Lancamentos": [
        "ID",
        "Data",
        "Tipo",
        "Categoria",
        "Subcategoria",
        "Descrição",
        "Valor",
        "Forma Pagamento",
    ],
    "Metas_Orcamento": [
        "Categoria",
        "Limite Mensal",
        "Alerta (%)",
    ],
    "Resumo_Mensal": [
        "Categoria",
        "Meta Mensal",
        "Gasto Mês Atual",
        "% Utilizado",
        "Status",
    ],
}

DEFAULT_MAINTENANCE_PLAN: list[list[Any]] = [
    ["Óleo e Filtro", 10000, 12, "", "", "", "", "Pendente"],
    ["Rodízio de Pneus", 10000, 6, "", "", "", "", "Pendente"],
    ["Filtro de Ar", 15000, 12, "", "", "", "", "Pendente"],
    ["Pastilhas de Freio", 30000, 24, "", "", "", "", "Pendente"],
    ["Correia Dentada", 60000, 48, "", "", "", "", "Pendente"],
]

DEFAULT_BUDGET_GOALS: list[list[Any]] = [
    ["Mercado", 0, 80],
    ["Saúde", 0, 80],
    ["Igreja", 0, 80],
    ["Casa", 0, 80],
    ["Lazer", 0, 80],
    ["Transporte", 0, 80],
    ["Outros", 0, 80],
]


def _parse_float(value: Any) -> float | None:
    """Parse numeric values supporting both dot and comma decimal separators."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("R$", "").strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    """Parse integer values safely from sheet cells."""
    parsed = _parse_float(value)
    return int(round(parsed)) if parsed is not None else None


def _add_months(date_str: str, months: int) -> str:
    """Add `months` calendar months to an ISO YYYY-MM-DD date string."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    total_months = (dt.month - 1) + months
    year = dt.year + total_months // 12
    month = (total_months % 12) + 1
    day = min(dt.day, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


class GoogleSheetsService:
    """Async-friendly wrapper around `gspread` for vehicle and budget spreadsheets."""

    def __init__(
        self,
        *,
        client: gspread.Client,
        car_spreadsheet_id: str | None = None,
        budget_spreadsheet_id: str | None = None,
        timezone_name: str = "America/Sao_Paulo",
    ) -> None:
        self._client = client
        self._car_id = car_spreadsheet_id
        self._budget_id = budget_spreadsheet_id
        self._timezone = ZoneInfo(timezone_name)

    @property
    def has_car_sheet(self) -> bool:
        """Return True if the vehicle spreadsheet ID is configured."""
        return bool(self._car_id)

    @property
    def has_budget_sheet(self) -> bool:
        """Return True if the budget spreadsheet ID is configured."""
        return bool(self._budget_id)

    def _open_worksheet(
        self, spreadsheet_key: Literal["car", "budget"], worksheet_name: str
    ) -> gspread.Worksheet:
        spreadsheet_id = self._car_id if spreadsheet_key == "car" else self._budget_id
        if not spreadsheet_id:
            raise ValueError(
                f"Spreadsheet ID for '{spreadsheet_key}' is not configured in environment."
            )
        spreadsheet = self._client.open_by_key(spreadsheet_id)
        return spreadsheet.worksheet(worksheet_name)

    def _get_last_odometer_sync(self) -> int | None:
        ws = self._open_worksheet("car", "Abastecimentos")
        records = ws.get_all_records()
        kms = [_parse_int(r.get("Km Atual")) for r in records]
        valid_kms = [km for km in kms if km is not None]
        return max(valid_kms) if valid_kms else None

    def _log_fuel_expense_sync(
        self,
        *,
        date: str,
        current_km: int,
        fuel_type: str,
        liters: float,
        total_value: float,
        station: str,
        notes: str,
    ) -> dict[str, Any]:
        ws = self._open_worksheet("car", "Abastecimentos")
        last_km = self._get_last_odometer_sync()

        km_driven: int | None = None
        consumption: float | None = None
        if last_km is not None and current_km > last_km:
            km_driven = current_km - last_km
            if liters > 0:
                consumption = round(km_driven / liters, 2)

        price_per_liter = round(total_value / liters, 2) if liters > 0 else 0.0
        record_id = uuid.uuid4().hex[:8]

        row = [
            record_id,
            date,
            current_km,
            fuel_type,
            round(liters, 2),
            round(total_value, 2),
            price_per_liter,
            station,
            km_driven if km_driven is not None else "",
            consumption if consumption is not None else "",
            notes,
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

        return {
            "status": "ok",
            "record_id": record_id,
            "spreadsheet": "car",
            "worksheet": "Abastecimentos",
            "date": date,
            "current_km": current_km,
            "fuel_type": fuel_type,
            "liters": round(liters, 2),
            "total_value": round(total_value, 2),
            "price_per_liter": price_per_liter,
            "km_driven": km_driven,
            "consumption_km_l": consumption,
        }

    async def log_fuel_expense(
        self,
        *,
        date: str,
        current_km: int,
        fuel_type: str,
        liters: float,
        total_value: float,
        station: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Append a fuel fill-up row and compute price/L, km driven, and consumption."""
        return await asyncio.to_thread(
            self._log_fuel_expense_sync,
            date=date,
            current_km=current_km,
            fuel_type=fuel_type,
            liters=liters,
            total_value=total_value,
            station=station,
            notes=notes,
        )

    def _update_maintenance_plan_sync(
        self,
        *,
        service_item: str,
        date: str,
        km: int | None,
        next_km: int | None,
        next_date: str | None,
    ) -> bool:
        plan_ws = self._open_worksheet("car", "Plano_Manutencao")
        records = plan_ws.get_all_records()
        needle = service_item.strip().lower()

        for idx, row in enumerate(records, start=2):
            item_name = str(row.get("Item", "")).strip()
            if not item_name:
                continue
            item_lower = item_name.lower()
            if needle in item_lower or item_lower in needle:
                interval_km = _parse_int(row.get("Intervalo Km"))
                interval_months = _parse_int(row.get("Intervalo Meses"))

                computed_next_km = next_km
                if computed_next_km is None and km is not None and interval_km:
                    computed_next_km = km + interval_km

                computed_next_date = next_date
                if computed_next_date is None and interval_months:
                    computed_next_date = _add_months(date, interval_months)

                plan_ws.update(
                    range_name=f"D{idx}:H{idx}",
                    values=[
                        [
                            km if km is not None else "",
                            date,
                            computed_next_km if computed_next_km is not None else "",
                            computed_next_date or "",
                            "Em dia",
                        ]
                    ],
                    value_input_option="USER_ENTERED",
                )
                return True
        return False

    def _log_car_expense_sync(
        self,
        *,
        expense_kind: Literal["maintenance", "fixed_or_other"],
        date: str,
        description: str,
        value: float,
        km: int | None,
        workshop: str,
        category: str,
        next_km: int | None,
        next_date: str | None,
        notes: str,
    ) -> dict[str, Any]:
        record_id = uuid.uuid4().hex[:8]

        if expense_kind == "maintenance":
            ws = self._open_worksheet("car", "Manutencoes_Realizadas")
            row = [
                record_id,
                date,
                km if km is not None else "",
                description,
                workshop,
                round(value, 2),
                next_km if next_km is not None else "",
                next_date or "",
                notes,
            ]
            ws.append_row(row, value_input_option="USER_ENTERED")
            plan_updated = self._update_maintenance_plan_sync(
                service_item=description,
                date=date,
                km=km,
                next_km=next_km,
                next_date=next_date,
            )
            return {
                "status": "ok",
                "record_id": record_id,
                "spreadsheet": "car",
                "worksheet": "Manutencoes_Realizadas",
                "date": date,
                "description": description,
                "value": round(value, 2),
                "plan_updated": plan_updated,
            }

        ws = self._open_worksheet("car", "Despesas_Fixas_Outros")
        row = [
            record_id,
            date,
            category or "Outros",
            description,
            round(value, 2),
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return {
            "status": "ok",
            "record_id": record_id,
            "spreadsheet": "car",
            "worksheet": "Despesas_Fixas_Outros",
            "date": date,
            "category": category or "Outros",
            "description": description,
            "value": round(value, 2),
        }

    async def log_car_expense(
        self,
        *,
        expense_kind: Literal["maintenance", "fixed_or_other"],
        date: str,
        description: str,
        value: float,
        km: int | None = None,
        workshop: str = "",
        category: str = "Outros",
        next_km: int | None = None,
        next_date: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Record a vehicle maintenance or fixed/other expense in Google Sheets."""
        return await asyncio.to_thread(
            self._log_car_expense_sync,
            expense_kind=expense_kind,
            date=date,
            description=description,
            value=value,
            km=km,
            workshop=workshop,
            category=category,
            next_km=next_km,
            next_date=next_date,
            notes=notes,
        )

    def _get_car_maintenance_status_sync(self, current_km: int | None) -> dict[str, Any]:
        effective_km = current_km if current_km is not None else self._get_last_odometer_sync()
        plan_ws = self._open_worksheet("car", "Plano_Manutencao")
        records = plan_ws.get_all_records()
        today = datetime.now(self._timezone).date()

        items: list[dict[str, Any]] = []
        for row in records:
            item_name = str(row.get("Item", "")).strip()
            if not item_name:
                continue

            next_km = _parse_int(row.get("Próximo Km"))
            next_date_str = str(row.get("Próxima Data", "")).strip()
            computed_status = str(row.get("Status", "Pendente")).strip() or "Pendente"

            if next_km is not None and effective_km is not None:
                remaining_km = next_km - effective_km
                if remaining_km <= 0:
                    computed_status = "Vencido (Km)"
                elif remaining_km <= 1000:
                    computed_status = f"Próximo ({remaining_km} km restantes)"

            if next_date_str:
                try:
                    next_dt = datetime.strptime(next_date_str, "%Y-%m-%d").date()
                    days_left = (next_dt - today).days
                    if days_left <= 0:
                        computed_status = "Vencido (Data)"
                    elif days_left <= 30 and "Vencido" not in computed_status:
                        computed_status = f"Próximo ({days_left} dias restantes)"
                except ValueError:
                    pass

            items.append(
                {
                    "item": item_name,
                    "last_km": _parse_int(row.get("Último Km")),
                    "last_date": str(row.get("Última Data", "")).strip() or None,
                    "next_km": next_km,
                    "next_date": next_date_str or None,
                    "status": computed_status,
                }
            )

        technical_notes: list[str] = []
        try:
            specs_ws = self._open_worksheet("car", "Especificacoes_e_Risco")
            for spec_row in specs_ws.get_all_values():
                joined = " | ".join(cell.strip() for cell in spec_row if cell.strip())
                if joined:
                    technical_notes.append(joined)
        except Exception:
            # Optional reference tab; absence does not affect core maintenance checks.
            pass

        return {
            "status": "ok",
            "current_km": effective_km,
            "items": items,
            "technical_notes": technical_notes[:20],
        }

    async def get_car_maintenance_status(self, current_km: int | None = None) -> dict[str, Any]:
        """Return upcoming and overdue vehicle maintenance items."""
        return await asyncio.to_thread(self._get_car_maintenance_status_sync, current_km)

    def _get_car_performance_summary_sync(self, last_n_refills: int = 5) -> dict[str, Any]:
        fuel_ws = self._open_worksheet("car", "Abastecimentos")
        fuel_records = fuel_ws.get_all_records()

        odometers: list[int] = []
        refills: list[dict[str, Any]] = []
        total_fuel_spent = 0.0
        total_liters_for_avg = 0.0
        total_km_for_avg = 0
        by_fuel: dict[str, dict[str, float | int]] = {}

        for row in fuel_records:
            km = _parse_int(row.get("Km Atual"))
            if km is not None:
                odometers.append(km)

            liters = _parse_float(row.get("Litros")) or 0.0
            total_value = _parse_float(row.get("Valor Total")) or 0.0
            price_per_l = _parse_float(row.get("Preço/L"))
            km_driven = _parse_int(row.get("Km Rodados"))
            km_per_l = _parse_float(row.get("Consumo (km/L)"))
            fuel_type = str(row.get("Combustível", "")).strip() or "Desconhecido"

            total_fuel_spent += total_value
            if km_driven and km_driven > 0 and liters > 0:
                total_km_for_avg += km_driven
                total_liters_for_avg += liters
                bucket = by_fuel.setdefault(
                    fuel_type,
                    {"refills": 0, "km_driven": 0, "liters": 0.0, "spent": 0.0},
                )
                bucket["refills"] = int(bucket["refills"]) + 1
                bucket["km_driven"] = int(bucket["km_driven"]) + km_driven
                bucket["liters"] = float(bucket["liters"]) + liters
                bucket["spent"] = float(bucket["spent"]) + total_value

            cost_per_km = (
                round(total_value / km_driven, 2) if km_driven and km_driven > 0 else None
            )
            refills.append(
                {
                    "date": str(row.get("Data", "")).strip(),
                    "km": km,
                    "fuel_type": fuel_type,
                    "liters": round(liters, 3) if liters else 0.0,
                    "total_value": round(total_value, 2),
                    "price_per_l": round(price_per_l, 2) if price_per_l is not None else None,
                    "km_driven": km_driven,
                    "km_per_l": round(km_per_l, 2) if km_per_l is not None else None,
                    "cost_per_km": cost_per_km,
                    "station": str(row.get("Posto", "")).strip(),
                    "notes": str(row.get("Observações", "")).strip(),
                }
            )

        maint_ws = self._open_worksheet("car", "Manutencoes_Realizadas")
        total_maint_spent = sum(
            _parse_float(r.get("Valor")) or 0.0 for r in maint_ws.get_all_records()
        )
        fixed_ws = self._open_worksheet("car", "Despesas_Fixas_Outros")
        total_fixed_spent = sum(
            _parse_float(r.get("Valor")) or 0.0 for r in fixed_ws.get_all_records()
        )

        initial_km = odometers[0] if odometers else None
        current_km = odometers[-1] if odometers else None
        total_km_monitored = (
            current_km - initial_km
            if initial_km is not None and current_km is not None and current_km >= initial_km
            else None
        )
        total_spent_all = total_fuel_spent + total_maint_spent + total_fixed_spent
        avg_cost_per_km = (
            round(total_spent_all / total_km_monitored, 2)
            if total_km_monitored and total_km_monitored > 0
            else None
        )
        weighted_avg_km_per_l = (
            round(total_km_for_avg / total_liters_for_avg, 2)
            if total_liters_for_avg > 0 and total_km_for_avg > 0
            else None
        )

        efficiency_by_fuel = {
            fuel: {
                "refills": data["refills"],
                "km_driven": data["km_driven"],
                "avg_km_per_l": round(float(data["km_driven"]) / float(data["liters"]), 2),
                "total_spent": round(float(data["spent"]), 2),
            }
            for fuel, data in by_fuel.items()
            if float(data["liters"]) > 0
        }

        return {
            "status": "ok",
            "initial_km": initial_km,
            "current_km": current_km,
            "total_km_monitored": total_km_monitored,
            "total_fuel_spent": round(total_fuel_spent, 2),
            "total_maintenance_spent": round(total_maint_spent, 2),
            "total_fixed_spent": round(total_fixed_spent, 2),
            "weighted_avg_km_per_l": weighted_avg_km_per_l,
            "avg_cost_per_km": avg_cost_per_km,
            "efficiency_by_fuel": efficiency_by_fuel,
            "recent_refills": refills[-last_n_refills:],
        }

    async def get_car_performance_summary(self, last_n_refills: int = 5) -> dict[str, Any]:
        """Return detailed fuel consumption evolution, accumulated totals, and cost per km."""
        return await asyncio.to_thread(self._get_car_performance_summary_sync, last_n_refills)

    def _log_budget_expense_sync(
        self,
        *,
        date: str,
        entry_type: Literal["Despesa", "Receita"],
        category: str,
        description: str,
        value: float,
        subcategory: str,
        payment_method: str,
    ) -> dict[str, Any]:
        ws = self._open_worksheet("budget", "Lancamentos")
        record_id = uuid.uuid4().hex[:8]
        row = [
            record_id,
            date,
            entry_type,
            category,
            subcategory,
            description,
            round(value, 2),
            payment_method,
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return {
            "status": "ok",
            "record_id": record_id,
            "spreadsheet": "budget",
            "worksheet": "Lancamentos",
            "date": date,
            "entry_type": entry_type,
            "category": category,
            "description": description,
            "value": round(value, 2),
        }

    async def log_budget_expense(
        self,
        *,
        date: str,
        entry_type: Literal["Despesa", "Receita"],
        category: str,
        description: str,
        value: float,
        subcategory: str = "",
        payment_method: str = "",
    ) -> dict[str, Any]:
        """Append a household budget entry to the `Lancamentos` worksheet."""
        return await asyncio.to_thread(
            self._log_budget_expense_sync,
            date=date,
            entry_type=entry_type,
            category=category,
            description=description,
            value=value,
            subcategory=subcategory,
            payment_method=payment_method,
        )

    def _get_budget_summary_sync(self, year_month: str | None) -> dict[str, Any]:
        target_ym = year_month or datetime.now(self._timezone).strftime("%Y-%m")
        entries_ws = self._open_worksheet("budget", "Lancamentos")
        goals_ws = self._open_worksheet("budget", "Metas_Orcamento")

        entries = entries_ws.get_all_records()
        goals = goals_ws.get_all_records()

        spent_by_cat: dict[str, float] = {}
        total_expenses = 0.0
        total_income = 0.0

        for row in entries:
            row_date = str(row.get("Data", "")).strip()
            if not row_date.startswith(target_ym):
                continue
            amount = _parse_float(row.get("Valor")) or 0.0
            entry_type = str(row.get("Tipo", "Despesa")).strip()
            category = str(row.get("Categoria", "Outros")).strip() or "Outros"

            if entry_type.lower() == "receita":
                total_income += amount
            else:
                total_expenses += amount
                spent_by_cat[category] = spent_by_cat.get(category, 0.0) + amount

        goals_map: dict[str, tuple[float, float]] = {}
        for row in goals:
            cat = str(row.get("Categoria", "")).strip()
            if cat:
                limit_val = _parse_float(row.get("Limite Mensal")) or 0.0
                alert_pct = _parse_float(row.get("Alerta (%)")) or 80.0
                goals_map[cat] = (limit_val, alert_pct)

        all_categories = list(dict.fromkeys([*goals_map.keys(), *spent_by_cat.keys()]))
        categories_summary: list[dict[str, Any]] = []
        for cat in all_categories:
            spent = round(spent_by_cat.get(cat, 0.0), 2)
            limit_val, alert_pct = goals_map.get(cat, (0.0, 80.0))
            pct_used = round((spent / limit_val) * 100, 1) if limit_val > 0 else None
            alert = False
            if pct_used is not None and pct_used >= alert_pct:
                alert = True
            categories_summary.append(
                {
                    "category": cat,
                    "spent": spent,
                    "monthly_limit": limit_val,
                    "percent_used": pct_used,
                    "near_or_over_limit": alert,
                }
            )

        return {
            "status": "ok",
            "year_month": target_ym,
            "total_expenses": round(total_expenses, 2),
            "total_income": round(total_income, 2),
            "balance": round(total_income - total_expenses, 2),
            "categories": categories_summary,
        }

    async def get_budget_summary(self, year_month: str | None = None) -> dict[str, Any]:
        """Aggregate monthly spending by category and compare against configured goals."""
        return await asyncio.to_thread(self._get_budget_summary_sync, year_month)

    def _delete_row_by_id_sync(
        self,
        spreadsheet_key: Literal["car", "budget"],
        worksheet_name: str,
        record_id: str,
    ) -> bool:
        ws = self._open_worksheet(spreadsheet_key, worksheet_name)
        id_column = ws.col_values(1)
        for row_idx, cell_value in enumerate(id_column, start=1):
            if row_idx == 1:
                continue
            if str(cell_value).strip() == record_id:
                ws.delete_rows(row_idx)
                return True
        return False

    async def delete_row_by_id(
        self,
        *,
        spreadsheet_key: Literal["car", "budget"],
        worksheet_name: str,
        record_id: str,
    ) -> bool:
        """Delete a row matching `record_id` in column 1 (used for Undo)."""
        return await asyncio.to_thread(
            self._delete_row_by_id_sync,
            spreadsheet_key,
            worksheet_name,
            record_id,
        )
