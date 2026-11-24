# Fase 0 — Setup Inicial e Infraestrutura

Esta fase estabelece a base pública, segura e reproduzível do projeto antes da implementação dos fluxos de negócio.

## Entregas Realizadas

1. **Configuração orientada a ambiente (`src/config.py` e `.env.example`)**
   - Todas as credenciais, preferências e IDs são carregados via variáveis de ambiente com `pydantic-settings` (zero hardcoding).
   - Suporte configurável para `LLM_PROVIDER`, `STT_PROVIDER`, `TIMEZONE`, `MORNING_SUMMARY_TIME` e `DATA_RETENTION_DAYS`.

2. **Containerização (`Dockerfile` e `docker-compose.yml`)**
   - Imagem `python:3.12-slim` rodando com usuário não-root (`appuser`).
   - Timezone do container sincronizado via `TZ=${TIMEZONE:-UTC}` com `tzdata` instalado.
   - Volumes persistentes para `./data` (SQLite) e `./credentials` (OAuth Google).

3. **Portal de Documentação (`Zensical`)**
   - Configurado via `zensical.toml` na raiz e serviço opcional `docs` no `docker-compose.yml` (`--profile docs`).

4. **Testes e Qualidade**
   - Suíte inicial em `tests/test_config.py` validada com `pytest` e `ruff`.
