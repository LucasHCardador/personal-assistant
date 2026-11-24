# Fase 3 — Google Calendar, Google Meet e Confirmação Inline

## Objetivo
Integrar o assistente ao **Google Calendar** e **Google Meet** para consultar, agendar, reagendar e cancelar compromissos (consultas, igreja, reuniões), aplicando política de confirmação *Human-in-the-loop* via botões inline no Telegram para convites com terceiros e exclusões.

---

## O que foi implementado

### 1. Cliente Google Calendar & Meet
- **[`src/integrations/google_calendar.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/integrations/google_calendar.py)**:
  - `GoogleCalendarService`: wrappers assíncronos (`asyncio.to_thread`) sobre a API `calendar` v3 (`calendarId="primary"`).
  - `list_events`: lista compromissos em um intervalo ISO 8601 com filtro opcional por texto (`q`).
  - `create_event`: cria eventos com suporte a lista de convidados (`sendUpdates="all"`) e geração automática de link do **Google Meet** via `conferenceData` (`hangoutsMeet`) e `conferenceDataVersion=1`, retornando `meet_link` / `hangoutLink`.
  - `update_event`: atualiza ou reagenda eventos via `patch`.
  - `delete_event`: remove um evento pelo `event_id`.

### 2. Schemas, Tools e Política de Confirmação
- **[`src/agent/tools/schemas.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/agent/tools/schemas.py)** e **[`src/agent/tools/registry.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/agent/tools/registry.py)**:
  - Schemas Pydantic estritos: `ListCalendarEventsInput`, `CreateCalendarEventInput`, `UpdateCalendarEventInput` e `DeleteCalendarEventInput`.
  - `ToolRegistry` habilita as 4 ferramentas de agenda quando `enable_calendar_tools=True`.
- **[`src/agent/tools/executor.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/agent/tools/executor.py)**:
  - **Confirmação obrigatória (`confirmation_required`)**: `create_calendar_event` com `attendees` não vazio e `delete_calendar_event` não executam imediatamente; gravam uma pendência na tabela `pending_confirmations` do SQLite.
  - **Execução direta + Undo**: compromissos pessoais sem convidados externos são criados imediatamente e registrados em `action_history` (`target_system="google_calendar"`), permitindo desfazer tanto pelo botão **`Desfazer`** quanto pela tool `undo_last_action`.

### 3. Persistência e Botões Inline no Telegram
- **[`src/storage/database.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/storage/database.py)**:
  - Tabela `pending_confirmations` e métodos `create_pending_confirmation`, `get_pending_confirmation` e `resolve_pending_confirmation`, além da limpeza automática em `purge_expired_data`.
- **[`src/bot/handlers.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/bot/handlers.py)** e **[`src/bot/app.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/bot/app.py)**:
  - Quando `AssistantStructuredReply.pending_confirmation_id` está preenchido, o bot envia botões inline **`Confirmar`** (`confirm:<id>`) e **`Cancelar`** (`cancel:<id>`).
  - `confirmation_callback` valida a propriedade do `user_id` e executa ou cancela a operação pendente com feedback claro (incluindo o link do Google Meet quando criado).

### 4. Wiring Independente no `src/main.py`
- As ferramentas de Google Calendar & Meet são ativadas automaticamente sempre que `credentials/token.json` estiver válido, mesmo que `GOOGLE_SHEETS_CAR_ID` e `GOOGLE_SHEETS_BUDGET_ID` não estejam configurados.

---

## Permissões OAuth e Exemplos de Uso

### Permissões OAuth
O fluxo `python -m scripts.auth_google` solicita o escopo `https://www.googleapis.com/auth/calendar`, suficiente para ler, criar, atualizar e excluir eventos e gerar links do Google Meet na agenda `primary`.

### Exemplos de comandos no Telegram
- *"Quais são meus compromissos de amanhã?"*
- *"Agende consulta médica sexta-feira das 14h às 15h na Clínica Central"* (execução direta com botão **Desfazer**)
- *"Marque uma reunião com joao@exemplo.com amanhã às 10h com Google Meet"* (exibe botões **Confirmar** / **Cancelar**)
- *"Cancele o evento da reunião de sexta"* (exibe botões **Confirmar** / **Cancelar**)
