# Fase 4 — Motor Proativo (Scheduler e Lembretes)

## Objetivo
Implementar o motor proativo no `APScheduler` para enviar o **resumo matinal diário**, **alertas antecipados de compromissos do Google Calendar**, **avisos de manutenção preventiva do carro** e **lembretes avulsos ou recorrentes** gerenciados via linguagem natural no Telegram.

---

## O que foi implementado

### 1. Persistência de Lembretes e Deduplicação (`src/storage/database.py`)
- **`ReminderRecord` e CRUD em `reminders`**:
  - `create_reminder`: cria lembretes avulsos (`once`) ou recorrentes (`daily`, `weekly`, `monthly`).
  - `list_reminders`: lista lembretes por usuário e status em ordem cronológica.
  - `cancel_reminder`: cancela lembretes pendentes validando o `user_id` proprietário.
  - `get_due_reminders`: retorna lembretes pendentes cujo `trigger_at` já foi atingido (comparação timezone-aware).
  - `mark_reminder_dispatched`: avança `trigger_at` para o próximo ciclo quando recorrente (`daily`, `weekly`, `monthly`) ou marca `status='sent'` quando único.
- **Deduplicação em `sent_notifications`**:
  - `has_notification_been_sent` e `mark_notification_sent` (`INSERT OR IGNORE`) evitam alertas repetidos de eventos e manutenções.

### 2. Tools de Lembretes (`src/agent/tools/`)
- **[`src/agent/tools/schemas.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/agent/tools/schemas.py)**: schemas Pydantic estritos `CreateReminderInput` (`title`, `trigger_at_iso`, `recurrence`), `ListRemindersInput` e `CancelReminderInput`.
- **[`src/agent/tools/registry.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/agent/tools/registry.py)**: `create_reminder`, `list_reminders` e `cancel_reminder` ficam sempre habilitadas por padrão, mesmo sem Google OAuth configurado.
- **[`src/agent/tools/executor.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/agent/tools/executor.py)**: normalização de datas sem fuso para `TIMEZONE` e execução direta no SQLite.

### 3. Motor Proativo e Formatadores HTML
- **[`src/scheduler/proactive.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/scheduler/proactive.py)**: `ProactiveNotifier` e `register_proactive_jobs` registrando 4 jobs no `AsyncIOScheduler`:
  - `proactive_morning_summary` (`cron` diário em `MORNING_SUMMARY_TIME` no `TIMEZONE`): envia agenda do dia, lembretes pendentes e itens de manutenção próximos/vencidos para `TELEGRAM_ALLOWED_USER_IDS`.
  - `proactive_upcoming_events` (`interval` de 5 min): alerta **24h antes** (janela 23h–24h) e **1h antes** (janela 50–65 min) de compromissos com horário definido, deduplicado em `sent_notifications`.
  - `proactive_car_maintenance` (`cron` diário em `MORNING_SUMMARY_TIME`): alerta itens vencidos ou próximos (`<= 1000 km` ou `<= 15 dias`), deduplicado por chave diária.
  - `proactive_due_reminders` (`interval` de 1 min): dispara lembretes vencidos e atualiza recorrência/status apenas após confirmação de envio pelo Telegram.
- **[`src/bot/formatters.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/bot/formatters.py)**: formatadores HTML determinísticos (`format_morning_summary`, `format_event_alert`, `format_maintenance_alert`, `format_reminder_notification`) com `html.escape()`.
- **[`src/main.py`](file:///home/lucas-cardador/projetos/personal-assistant/src/main.py)**: inicialização do `ProactiveNotifier` e registro dos jobs dentro de `on_startup`.

---

## Configuração e Exemplos de Uso

### Variáveis de Ambiente
- `TIMEZONE`: fuso horário IANA usado pelos jobs `cron` e formatação de horários (ex.: `America/Sao_Paulo`).
- `MORNING_SUMMARY_TIME`: horário diário do resumo matinal e verificação de manutenção no formato `HH:MM` (ex.: `07:30`).
- `TELEGRAM_ALLOWED_USER_IDS`: lista de IDs autorizados que recebem os broadcasts proativos.

### Exemplos no Telegram
- *"Me lembra amanhã às 09:00 de ligar para o mecânico"*
- *"Cria um lembrete semanal toda segunda às 08:00 para revisar o orçamento"*
- *"Quais são os meus lembretes pendentes?"*
- *"Cancela o lembrete 3"*
