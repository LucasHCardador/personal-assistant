# Plano de Implementação — Fase 3: Google Calendar, Google Meet e Confirmação Inline

## Objetivo
Integrar o assistente ao **Google Calendar** e **Google Meet** para consultar, agendar, reagendar e cancelar compromissos (consultas, igreja, reuniões) com política de confirmação via botões inline no Telegram para convites com terceiros e exclusões.

## Tasks

1. **Cliente Google Calendar & Meet (`src/integrations/google_calendar.py`)**
   - Implementar `GoogleCalendarService` (wrappers assíncronos via `asyncio.to_thread`) usando `googleapiclient.discovery.build("calendar", "v3", credentials=creds)`.
   - Métodos:
     - `list_events(start_iso, end_iso, query=None)`
     - `create_event(summary, start_iso, end_iso, description=None, location=None, attendees=None, create_meet=False)` (usando `conferenceDataVersion=1` e `createRequest` com `hangoutsMeet` quando `create_meet=True`)
     - `update_event(event_id, ...)`
     - `delete_event(event_id)`

2. **Schemas e Tools de Agenda (`src/agent/tools/schemas.py`, `registry.py`, `executor.py`)**
   - Definir schemas Pydantic estritos: `ListCalendarEventsInput`, `CreateCalendarEventInput`, `UpdateCalendarEventInput`, `DeleteCalendarEventInput`.
   - Implementar política de confirmação (*Human-in-the-loop*):
     - `create_calendar_event` **com `attendees` não vazio** e `delete_calendar_event` **sempre** retornam status `confirmation_required`, salvando uma ação pendente no SQLite (`pending_confirmations`) sem executar imediatamente no Google Calendar.
     - Eventos pessoais sem convidados externos e atualizações simples executam direto, registrando `action_history` para Undo quando aplicável.

3. **Persistência de Confirmações Pendentes e Botões Inline (`src/storage/database.py`, `src/bot/handlers.py`)**
   - Criar tabela `pending_confirmations (id, user_id, tool_name, args_json, summary_text, status, created_at)` no `Database`.
   - No `BotHandlers`, quando `AssistantStructuredReply` / `ToolExecutionContext` indicar `pending_confirmation_id`, exibir botões inline `[Confirmar]` (`confirm:<id>`) e `[Cancelar]` (`cancel:<id>`).
   - Implementar `confirmation_callback` no `BotHandlers` validando propriedade do `user_id` e executando ou cancelando a ação com feedback claro.

4. **Wiring no `src/main.py` e `AgentOrchestrator`**
   - Registrar as tools de Calendar/Meet em `src/main.py` quando `token.json` estiver disponível (degradação graciosa se não configurado).
   - Suportar `pending_confirmation_id` no `AgentOrchestrator` e `AssistantStructuredReply` (ou contexto de execução de tools).

5. **Testes Unitários (`tests/test_calendar_and_confirmations.py`)**
   - Testar `GoogleCalendarService` (mock do client v3), criação de link do Meet (`conferenceData`), fluxo de confirmação pendente para convites externos e exclusões, execução direta sem convidados, e callbacks `confirm:` / `cancel:`.

6. **Documentação (`docs/phases/fase-3-calendar-meet.md`, `zensical.toml`, `README.md`)**
   - Documentar permissões OAuth, geração automática de links do Google Meet, política de confirmação por botões inline e exemplos de uso.
