# Personal Assistant

A self-hosted personal assistant connected to **Telegram**, powered by **Gemini** multimodal AI, and integrated with the **Google ecosystem** (Calendar, Meet, and Sheets).

Designed to run 24/7 via Docker on a VPS or home server, with all personal data, credentials, and preferences strictly externalized via environment variables.

## Features (Planned & Modular)

- **Multimodal Telegram Interface**: Understands free-form text, voice messages, and receipt/odometer photos natively via Gemini.
- **Google Calendar & Meet**: Schedules appointments, checks upcoming events, and generates Google Meet links (with inline confirmation buttons for external invites or deletions).
- **Google Sheets (Car & Household Budget)**: Logs fuel refills, vehicle maintenance, and daily expenses into structured spreadsheets.
- **Proactive Scheduler**: Sends daily morning summaries, upcoming event alerts, vehicle preventive maintenance reminders (by mileage and date), and custom recurring reminders.
- **User Whitelist**: Restricts bot access to authorized Telegram user IDs configured in `.env`.

## Architecture

```text
personal-assistant/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env.example
├── docs/
│   └── research/          # Architecture Decision Records (ADRs)
├── scripts/               # One-off OAuth and Google Sheets setup scripts
├── src/
│   ├── main.py            # Service entrypoint
│   ├── config.py          # Environment-driven configuration (Pydantic)
│   ├── bot/               # Telegram handlers, whitelist middleware, inline callbacks
│   ├── agent/             # Gemini multimodal client, prompts, and tool registry
│   ├── integrations/      # Google OAuth 2.0, Calendar/Meet, and Sheets clients
│   ├── scheduler/         # Proactive background jobs (APScheduler)
│   └── storage/           # Local SQLite persistence (reminders, undo history)
└── tests/                 # Automated test suite
```

For full architectural details, see [docs/research/adr-001-arquitetura-e-viabilizacao.md](docs/research/adr-001-arquitetura-e-viabilizacao.md).

## Prerequisites

1. **Docker & Docker Compose** (recommended) or **Python 3.12+**.
2. **Telegram Bot Token**: Create a bot with [@BotFather](https://t.me/BotFather) and get your numeric user ID via [@userinfobot](https://t.me/userinfobot).
3. **Gemini API Key**: Generate a key in [Google AI Studio](https://aistudio.google.com/).
4. **Google Cloud OAuth 2.0 Credentials**:
   - Create a project in [Google Cloud Console](https://console.cloud.google.com/).
   - Enable **Google Calendar API**, **Google Sheets API**, and **Google Drive API**.
   - Create an OAuth 2.0 Client ID (Desktop App) and download the JSON file as `credentials/credentials.json`.

## Quick Start

1. **Clone the repository and configure your environment:**

   ```bash
   cp .env.example .env
   mkdir -p credentials data
   ```

   Edit `.env` with your `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`, `GEMINI_API_KEY`, and preferred `TIMEZONE`.

2. **Run with Docker Compose:**

   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```

3. **Run locally (without Docker):**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   python -m src.main
   ```

4. **Run tests & linter:**

   ```bash
   pytest
   ruff check .
   ```

## License

MIT
