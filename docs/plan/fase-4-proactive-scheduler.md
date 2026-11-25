# Plano de Implementação — Fase 4: Motor Proativo (Scheduler e Lembretes)

## Objetivo
Implementar o motor proativo no `APScheduler` para enviar o **resumo matinal diário**, **alertas antecipados de compromissos do Google Calendar**, **avisos de manutenção preventiva do carro** (por quilometragem e data) e **lembretes avulsos ou recorrentes** gerenciados via linguagem natural no Telegram.

## Tasks

1. **Persistência de Lembretes e Notificações (`src/storage/database.py`)**
   - Adicionar métodos CRUD para `reminders`: `create_reminder`, `list_reminders`, `cancel_reminder`, `get_due_reminders`, `mark_reminder_sent` (ou atualizar `trigger_at` quando recorrente: `daily`, `weekly`, `monthly`).
   - Adicionar métodos para `sent_notifications`: `has_notification_been_sent(key)` e `mark_notification_sent(key)` para evitar alertas duplicados.

2. **Tools de Lembretes (`src/agent/tools/schemas.py`, `registry.py`, `executor.py`)**
   - Criar schemas Pydantic estritos: `CreateReminderInput`, `ListRemindersInput`, `CancelReminderInput`.
   - Registrar as tools de lembretes sempre ativas no `ToolRegistry` (independentes de Google OAuth).
   - Integrar no `ToolExecutor` para criar, listar e cancelar lembretes do usuário no SQLite.

3. **Motor Proativo e Formatadores (`src/scheduler/proactive.py` e `src/bot/formatters.py`)**
   - Criar `ProactiveNotifier` recebendo `bot` (Telegram `Bot`), `database`, `settings`, `calendar_service` (opcional) e `sheets_service` (opcional):
     - **Job 1 — Resumo Matinal** (`cron` diário no horário `MORNING_SUMMARY_TIME` no `TIMEZONE`): envia agenda do dia (Calendar), lembretes pendentes do dia e manutenções próximas/vencidas para os `telegram_allowed_user_ids`.
     - **Job 2 — Alertas Antecipados de Agenda** (`interval` a cada 5 min): verifica eventos nas próximas 24h; envia alerta **1 dia antes** (janela 23h–24h) e **1 hora antes** (janela 50–65 min), deduplicado por `sent_notifications`.
     - **Job 3 — Monitor de Manutenção Veicular** (`cron` diário): verifica `get_car_maintenance_status` e notifica itens próximos (ex: <= 1000 km ou <= 15 dias) ou vencidos, deduplicado por chave diária/mensal em `sent_notifications`.
     - **Job 4 — Lembretes Avulsos/Recorrentes** (`interval` a cada 1 min): dispara lembretes cujo `trigger_at <= now` e avança `trigger_at` se recorrente ou marca `sent` se único.
   - Criar formatadores determinísticos HTML em `src/bot/formatters.py` para resumo matinal, alerta de evento, alerta de manutenção e lembrete disparado.

4. **Wiring no `src/main.py` e `src/scheduler/housekeeping.py`**
   - Registrar os jobs proativos no `AsyncIOScheduler` dentro do `on_startup` (quando `app.bot` já está disponível).

5. **Testes Unitários (`tests/test_proactive_scheduler.py`)**
   - Testar CRUD de `reminders` e avanço de recorrência (`daily`, `weekly`, `monthly`).
   - Testar deduplicação em `sent_notifications`.
   - Testar `ToolExecutor` para criar/listar/cancelar lembretes.
   - Testar `ProactiveNotifier` (resumo matinal, alerta de evento 1h/24h antes sem duplicar, alerta de manutenção e disparo de lembrete) com mocks de `Bot`, `GoogleCalendarService` e `GoogleSheetsService`.

6. **Documentação (`docs/phases/fase-4-proactive-scheduler.md`, `zensical.toml`, `README.md`)**
   - Documentar os jobs proativos, configuração de `MORNING_SUMMARY_TIME` e `TIMEZONE`, e exemplos de lembretes no Zensical e `README.md`.
