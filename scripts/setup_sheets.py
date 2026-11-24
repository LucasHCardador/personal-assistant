"""CLI script to provision Google Sheets spreadsheets for vehicle and budget tracking."""

import argparse
import os
from pathlib import Path
from typing import Any

import gspread

from src.integrations.google_auth import load_google_credentials
from src.integrations.google_sheets import (
    BUDGET_SPREADSHEET_TITLE,
    BUDGET_WORKSHEET_HEADERS,
    CAR_SPREADSHEET_TITLE,
    CAR_WORKSHEET_HEADERS,
    DEFAULT_BUDGET_GOALS,
    DEFAULT_MAINTENANCE_PLAN,
)


def _resolve_default_paths() -> tuple[Path, Path]:
    creds_env = os.getenv("GOOGLE_CREDENTIALS_PATH")
    token_env = os.getenv("GOOGLE_TOKEN_PATH")
    creds_path = Path(creds_env) if creds_env else Path("credentials/credentials.json")
    token_path = Path(token_env) if token_env else Path("credentials/token.json")
    return creds_path, token_path


def _populate_spreadsheet(
    spreadsheet: gspread.Spreadsheet,
    headers_map: dict[str, list[str]],
    seed_rows: dict[str, list[list[Any]]] | None = None,
) -> None:
    """Create/rename worksheets, write headers, freeze row 1, and seed initial rows."""
    existing_sheets = spreadsheet.worksheets()
    first_sheet = existing_sheets[0] if existing_sheets else None

    for idx, (sheet_name, headers) in enumerate(headers_map.items()):
        if idx == 0 and first_sheet is not None:
            ws = first_sheet
            ws.update_title(sheet_name)
        else:
            try:
                ws = spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                ws = spreadsheet.add_worksheet(
                    title=sheet_name, rows=200, cols=max(len(headers), 10)
                )

        ws.update(range_name="A1", values=[headers], value_input_option="USER_ENTERED")
        ws.freeze(rows=1)

        if seed_rows and sheet_name in seed_rows and seed_rows[sheet_name]:
            existing_values = ws.get_all_values()
            if len(existing_values) <= 1:
                ws.append_rows(seed_rows[sheet_name], value_input_option="USER_ENTERED")


def create_spreadsheets(client: gspread.Client) -> tuple[str, str]:
    """Create both vehicle and budget spreadsheets and return `(car_id, budget_id)`."""
    car_sheet = client.create(CAR_SPREADSHEET_TITLE)
    _populate_spreadsheet(
        car_sheet,
        CAR_WORKSHEET_HEADERS,
        seed_rows={"Plano_Manutencao": DEFAULT_MAINTENANCE_PLAN},
    )

    budget_sheet = client.create(BUDGET_SPREADSHEET_TITLE)
    resumo_rows = [
        [
            f"=Metas_Orcamento!A{row_idx}",
            f"=Metas_Orcamento!B{row_idx}",
            (
                '=SUMIFS(Lancamentos!$G:$G; Lancamentos!$C:$C; "Despesa"; '
                f'Lancamentos!$D:$D; A{row_idx})'
            ),
            f"=IF(B{row_idx}>0; C{row_idx}/B{row_idx}; 0)",
            (
                f'=IF(B{row_idx}=0; "Sem meta"; '
                f'IF(D{row_idx}>=Metas_Orcamento!C{row_idx}/100; "Alerta"; "OK"))'
            ),
        ]
        for row_idx in range(2, 2 + len(DEFAULT_BUDGET_GOALS))
    ]
    _populate_spreadsheet(
        budget_sheet,
        BUDGET_WORKSHEET_HEADERS,
        seed_rows={
            "Metas_Orcamento": DEFAULT_BUDGET_GOALS,
            "Resumo_Mensal": resumo_rows,
        },
    )

    return car_sheet.id, budget_sheet.id


def main() -> None:
    """Authenticate with Google and provision the two spreadsheets."""
    default_creds, default_token = _resolve_default_paths()

    parser = argparse.ArgumentParser(
        description=(
            "Provision 'Assistente - Controle Veicular' and "
            "'Assistente - Orçamento Doméstico' in Google Sheets."
        )
    )
    parser.add_argument("--credentials", type=Path, default=default_creds)
    parser.add_argument("--token", type=Path, default=default_token)
    args = parser.parse_args()

    creds = load_google_credentials(args.credentials, args.token)
    client = gspread.authorize(creds)
    car_id, budget_id = create_spreadsheets(client)

    print("Planilhas criadas com sucesso! Adicione as linhas abaixo ao seu .env:")
    print(f"GOOGLE_SHEETS_CAR_ID={car_id}")
    print(f"GOOGLE_SHEETS_BUDGET_ID={budget_id}")


if __name__ == "__main__":
    main()
