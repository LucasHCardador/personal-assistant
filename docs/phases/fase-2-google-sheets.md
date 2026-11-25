# Fase 2 — Google Sheets, Tool Calling e Undo

## Objetivo
Conectar o assistente ao **Google OAuth 2.0** e ao **Google Sheets** para registrar e consultar dados reais de **Controle Veicular e Manutenção** e **Orçamento Doméstico**, com validação estrita via Pydantic e suporte a **Desfazer (Undo)** tanto por botão inline no Telegram quanto por comando em linguagem natural.

---

## O que foi implementado

### 1. Autenticação Google OAuth 2.0
- **[`src/integrations/google_auth.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/integrations/google_auth.py)**: carrega `token.json`, renova automaticamente o `access_token` usando o `refresh_token` quando expirado e executa o fluxo inicial OAuth 2.0 com os escopos `calendar`, `spreadsheets` e `drive.file`.
- **`scripts/auth_google.py`**: CLI para bootstrap inicial do `credentials/token.json` a partir do `credentials/credentials.json`.

### 2. Cliente Google Sheets e Provisionamento
- **`scripts/setup_sheets.py`**: cria automaticamente as duas planilhas no Google Drive do usuário:
  - **`Assistente - Controle Veicular`**: abas `Abastecimentos`, `Manutencoes_Realizadas`, `Plano_Manutencao` (com itens padrão) e `Despesas_Fixas_Outros`.
  - **`Assistente - Orçamento Doméstico`**: abas `Lancamentos`, `Metas_Orcamento` (com categorias padrão) e `Resumo_Mensal` (com fórmulas `SUMIFS`).
- **[`src/integrations/google_sheets.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/integrations/google_sheets.py)**:
  - `log_fuel_expense`: calcula automaticamente `Preço/L`, `Km Rodados` (comparando com o último odômetro registrado) e `Consumo (km/L)`.
  - `log_car_expense`: registra manutenções (atualizando `Plano_Manutencao`) ou despesas fixas (`IPVA`, `Seguro`, `Lavagem`, `Estacionamento`, `Multa`).
  - `get_car_maintenance_status`: avalia itens próximos do vencimento ou vencidos por km e data.
  - `log_budget_expense` e `get_budget_summary`: registra lançamentos e agrega gastos do mês por categoria comparando com `Metas_Orcamento`.
  - `delete_row_by_id`: remove uma linha por `ID` para suportar o fluxo de Undo.

### 3. Tool Calling Multi-LLM e Undo
- **`src/agent/tools/`**:
  - `schemas.py`: modelos Pydantic estritos (`FuelExpenseInput`, `CarExpenseInput`, `MaintenanceStatusQuery`, `BudgetExpenseInput`, `BudgetSummaryQuery`, `UndoActionInput`).
  - `registry.py` (`ToolRegistry`) e `executor.py` (`ToolExecutor`): registram as ferramentas ativas conforme os IDs de planilha configurados e gravam ações reversíveis na tabela `action_history` do SQLite (`Database.record_action`, `Database.get_last_undoable_action`, `Database.mark_action_undone`).
- **Provedores e Orquestrador**:
  - `BaseLLMProvider`, `GeminiProvider`, `AnthropicProvider`, `OpenAICompatibleProvider` e `AgentOrchestrator` suportam loop de *Function Calling* (máximo de 5 iterações) mantendo `AssistantStructuredReply` na resposta final.
  - Se `token.json` ou os IDs das planilhas não estiverem configurados no `.env`, o serviço inicia normalmente registrando um aviso no log e mantendo o modo conversacional ativo.

### 4. Botão Inline `Desfazer` no Telegram
- **`src/bot/handlers.py`** e **`src/bot/app.py`**: quando uma gravação em planilha é executada com sucesso, a resposta no Telegram inclui o botão inline **`Desfazer`** (`CallbackQueryHandler` com padrão `^undo:\d+$`), removendo a linha correspondente da planilha e marcando a ação como desfeita no SQLite.

---

## Como Configurar

1. Coloque seu `credentials.json` (OAuth 2.0 Desktop App do Google Cloud Console) em `credentials/credentials.json`.
2. Gere o `token.json`:
   ```bash
   python -m scripts.auth_google
   ```
3. Crie as planilhas e copie os IDs exibidos para o seu `.env`:
   ```bash
   python -m scripts.setup_sheets
   ```
4. Preencha no `.env`:
   ```env
   GOOGLE_SHEETS_CAR_ID=...
   GOOGLE_SHEETS_BUDGET_ID=...
   ```
