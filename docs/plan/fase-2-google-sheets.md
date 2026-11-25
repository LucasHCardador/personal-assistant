# Plano de Implementação — Fase 2: Google Sheets, Tool Calling e Undo

## Objetivo
Integrar o assistente ao Google OAuth 2.0 e Google Sheets para gerenciar o **Controle Veicular e Manutenção** e o **Orçamento Doméstico**, conectando o agente a ferramentas reais (*Function Calling*) com validação Pydantic estrita e suporte a desfazer (`undo`).

## Tasks

1. **Autenticação Google OAuth 2.0 (`src/integrations/google_auth.py` e `scripts/auth_google.py`)**
   - Gerenciar credenciais OAuth 2.0 (`credentials.json` e `token.json`) com renovação automática de `refresh_token` para escopos de Calendar, Sheets e Drive (`drive.file`).
   - Criar `scripts/auth_google.py` para bootstrap inicial do `token.json`.

2. **Cliente Google Sheets e Provisionamento (`src/integrations/google_sheets.py` e `scripts/setup_sheets.py`)**
   - Criar `scripts/setup_sheets.py` para gerar as duas planilhas estruturadas (`Assistente - Controle Veicular` e `Assistente - Orçamento Doméstico`) com abas e cabeçalhos conforme `ADR-001`.
   - Implementar métodos de leitura e escrita para:
     - `Abastecimentos` (com cálculo automático de km rodados e consumo km/L usando o último odômetro)
     - `Manutencoes_Realizadas`, `Plano_Manutencao` e `Despesas_Fixas_Outros`
     - `Lancamentos` e `Metas_Orcamento` (orçamento doméstico)
     - Remoção de linha por ID para suportar Undo.

3. **Camada de Tools e Registry (`src/agent/tools/`)**
   - Definir schemas Pydantic estritos (`FuelExpenseInput`, `CarExpenseInput`, `BudgetExpenseInput`, `BudgetSummaryQuery`, `MaintenanceStatusQuery`, `UndoActionInput`).
   - Implementar `ToolRegistry` e `ToolExecutor` integrando com `Database` (`action_history` para Undo) e `GoogleSheetsService`.
   - Atualizar `BaseLLMProvider`, `GeminiProvider`, `AnthropicProvider`, `OpenAICompatibleProvider` e `AgentOrchestrator` para suportar loop de *Function Calling* mantendo `AssistantStructuredReply` na resposta final.

4. **UX no Telegram e Undo (`src/bot/handlers.py` e `src/bot/formatters.py`)**
   - Adicionar botão inline `Desfazer` quando um lançamento for gravado com sucesso, além de suporte ao comando/intenção de desfazer.

5. **Testes Unitários (`tests/`)**
   - Testar `GoogleSheetsService` (com mock de `gspread`), `ToolExecutor`, loop de tool calling no `AgentOrchestrator` e fluxo de `undo`.

6. **Documentação (`docs/phases/fase-2-google-sheets.md`, `zensical.toml`, `README.md`)**
   - Documentar setup do OAuth 2.0, `scripts/auth_google.py`, `scripts/setup_sheets.py` e uso das planilhas no Zensical e `README.md`.
