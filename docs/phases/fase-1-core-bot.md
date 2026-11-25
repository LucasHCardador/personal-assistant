# Fase 1 — Core do Bot, Multi-Provedor de IA e Governança

Esta fase implementa o núcleo conversacional do assistente no Telegram, com suporte a múltiplos provedores de IA, mídia efêmera em memória, saídas estruturadas e higienização automática de dados locais.

## Entregas Realizadas

1. **Bot Telegram e Segurança (`src/bot/`)**
   - Middleware de autorização estrita via `TELEGRAM_ALLOWED_USER_IDS` (`src/bot/middleware.py`).
   - Handlers para `/start`, `/help`, `/clear`, texto livre, mensagens de voz/áudio e fotos (`src/bot/handlers.py`).
   - Formatadores HTML determinísticos (`src/bot/formatters.py`) garantindo layout padronizado nas respostas.

2. **Camada Multi-Provedor de LLM e STT (`src/agent/`)**
   - Interface única `BaseLLMProvider` (`src/agent/providers/base.py`) com fábrica configurável via `.env`:
     - `gemini`: padrão gratuito e multimodal nativo (texto, imagem e áudio).
     - `anthropic`: suporte ao Claude (texto e visão nativos; áudio via fallback STT).
     - `openai_compatible`: suporte a OpenAI, OpenRouter (`:free`), Groq e Ollama local.
   - Fallback de transcrição de áudio (`src/agent/stt.py`) via Groq Whisper ou OpenAI Whisper quando o provedor escolhido não aceita áudio nativamente.

3. **Saídas Estruturadas (`src/agent/schemas.py`)**
   - Contrato Pydantic `AssistantStructuredReply` (`intent`, `summary`, `details`, `next_step_hint`) aplicado em todos os provedores.

4. **Governança e Higienização (`src/storage/` e `src/scheduler/housekeeping.py`)**
   - Mídia efêmera em memória (`ephemeral_memory_buffer` usando `BytesIO` descartado no bloco `finally`).
   - Persistência apenas de turnos textuais em SQLite (`src/storage/database.py`).
   - Job periódico (`AsyncIOScheduler`) que remove arquivos temporários residuais e expurga registros mais antigos que `DATA_RETENTION_DAYS`.
