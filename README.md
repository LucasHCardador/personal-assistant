# Personal Assistant

Assistente pessoal self-hosted conectado ao **Telegram**, com inteligência multimodal via **Gemini** e integrado ao **ecossistema Google** (Google Calendar, Google Meet e Google Sheets).

O projeto foi desenhado para rodar 24/7 em container Docker (em uma VPS, servidor Linux ou máquina local), mantendo todas as credenciais, preferências e identificadores estritamente em variáveis de ambiente (`.env`).

---

## Escopo e Para que Serve

O objetivo do assistente é centralizar a organização pessoal e familiar diretamente no **Telegram** — eliminando a necessidade de abrir planilhas, apps de agenda ou anotações separadas no meio da rotina.

### Como ele auxilia no dia a dia

1. **Controle Veicular e Plano de Manutenção (Google Sheets)**
   - Registre abastecimentos informando valor, litros e quilometragem atual (por texto, áudio ou foto do cupom/painel).
   - Acompanhe despesas como seguro, IPVA, lavagem e revisões.
   - Receba alertas proativos quando a quilometragem ou a data se aproximarem da próxima troca de óleo, rodízio de pneus ou revisão preventiva.

2. **Orçamento Doméstico e Gastos Diários (Google Sheets)**
   - Envie mensagens rápidas ao sair do mercado, farmácia ou restaurante (ex: *"Gastei R$ 245 no mercado hoje no débito"* ou foto da nota fiscal).
   - Os lançamentos são categorizados automaticamente em uma planilha orçamentária com metas mensais e resumo por categoria.

3. **Agenda, Consultas e Reuniões (Google Calendar & Google Meet)**
   - Agende compromissos pessoais, consultas médicas da família, eventos da igreja e reuniões por linguagem natural.
   - Crie eventos já com link do **Google Meet** e convide participantes (com confirmação rápida por botões no Telegram antes de enviar convites externos ou excluir eventos).

4. **Lembretes Proativos e Resumo Matinal**
   - Receba um resumo diário no horário configurado em `MORNING_SUMMARY_TIME` com os compromissos do dia, lembretes e alertas do carro.
   - Receba notificações antecipadas de compromissos e crie lembretes avulsos ou recorrentes direto pelo chat.

---

## Arquitetura do Projeto

```text
personal-assistant/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env.example
├── docs/
│   └── research/          # Architecture Decision Records (ADRs)
├── scripts/               # Scripts utilitários (OAuth Google e setup das planilhas)
├── src/
│   ├── main.py            # Entrypoint da aplicação
│   ├── config.py          # Configurações via variáveis de ambiente (Pydantic)
│   ├── bot/               # Handlers do Telegram, whitelist e botões inline
│   ├── agent/             # Cliente Gemini multimodal, prompts e registry de tools
│   ├── integrations/      # Integrações Google (OAuth 2.0, Calendar/Meet, Sheets)
│   ├── scheduler/         # Motor proativo (resumo matinal, alertas e manutenções)
│   └── storage/           # Persistência local SQLite (lembretes, histórico de undo)
└── tests/                 # Suíte de testes automatizados
```

Para detalhes completos da arquitetura e decisões técnicas, consulte [docs/research/adr-001-arquitetura-e-viabilizacao.md](docs/research/adr-001-arquitetura-e-viabilizacao.md).

---

## Pré-requisitos

1. **Docker e Docker Compose** (recomendado) ou **Python 3.12+**.
2. **Conta no Telegram** para criar o bot e obter seu ID numérico.
3. **Provedor de IA (Padrão 100% Gratuito)**:
   - **Recomendado (Gratuito e Multimodal)**: chave de API do **Gemini** no [Google AI Studio](https://aistudio.google.com/) (processa texto, áudio e fotos nativamente).
   - **Outros provedores suportados**: **Claude (Anthropic)**, **OpenRouter (`:free`)**, **Groq** ou **Ollama** (local) configuráveis via `.env`. Caso o provedor escolhido não aceite áudio nativo, você pode configurar `STT_PROVIDER=groq` (tier gratuito) para transcrição automática.
4. **Projeto no Google Cloud Console** (para integração com Calendar, Meet e Sheets):
   - Ative as APIs: **Google Calendar API**, **Google Sheets API** e **Google Drive API**.
   - Crie um **ID do cliente OAuth 2.0** (tipo *App para computador / Desktop App*) e salve o arquivo JSON como `credentials/credentials.json`.

---

## Como Linkar com o Telegram

1. **Criar o Bot**:
   - Abra o [@BotFather](https://t.me/BotFather) no Telegram.
   - Envie `/newbot`, escolha um nome e um `@username` terminado em `bot`.
   - Copie o **Token HTTP da API** gerado.

2. **Descobrir seu User ID (Whitelist)**:
   - Por segurança, o assistente só responde aos IDs autorizados em `TELEGRAM_ALLOWED_USER_IDS`.
   - Envie `/start` para o [@userinfobot](https://t.me/userinfobot) no Telegram e copie o número do seu `Id`.

3. **Configurar o `.env`**:
   - Preencha `TELEGRAM_BOT_TOKEN` com o token do `@BotFather`.
   - Preencha `TELEGRAM_ALLOWED_USER_IDS` com o seu ID numérico (para múltiplos usuários, separe por vírgula: `123456789,987654321`).

---

## Como Subir o Projeto

### 1. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` preenchendo no mínimo:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- `LLM_PROVIDER` (`gemini` por padrão, ou `anthropic` / `openai_compatible`)
- `LLM_API_KEY` e `LLM_MODEL`
- `TIMEZONE` (ex: `America/Sao_Paulo` — usado pela aplicação e também repassado como `TZ` ao container Docker)
- `MORNING_SUMMARY_TIME` (ex: `07:30`)

### 2. Subir com Docker Compose (Recomendado)

```bash
docker compose up -d --build
docker compose logs -f
```

Para parar o serviço:

```bash
docker compose down
```

### 3. Rodar localmente (sem Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m src.main
```

### 4. Testes e Linter

```bash
pytest
ruff check .
```

---

## Servidor de Documentação (Zensical)

O projeto utiliza o **[Zensical](https://zensical.org/)** para servir a documentação técnica e os registros de cada fase do desenvolvimento a partir da pasta `docs/` (configurado em `zensical.toml`).

### Subir o servidor de documentação via Docker Compose

```bash
docker compose --profile docs up
```

Ou diretamente via `docker run`:

```bash
docker run --rm -it -p 8000:8000 -v ${PWD}:/docs zensical/zensical
```

Após subir, acesse **http://localhost:8000** no navegador. As alterações nos arquivos Markdown em `docs/` são recarregadas automaticamente.

Para gerar os arquivos estáticos da documentação:

```bash
docker run --rm -it -v ${PWD}:/docs zensical/zensical build
```

---

## Como Usar no Dia a Dia

Depois de iniciar o serviço e abrir o chat do seu bot no Telegram, basta enviar mensagens em linguagem natural (texto, áudio ou foto):

- **Abastecimento**: *"Abasteci R$ 220 de gasolina no km 48.350, deu 36,5 litros"* (ou envie foto do cupom/painel).
- **Mercado / Orçamento**: *"Gastei 189,90 no supermercado hoje no cartão de crédito"*.
- **Agenda / Consultas**: *"Marca consulta do pediatra na quinta-feira às 14h"*.
- **Reunião no Google Meet**: *"Agenda um Meet com fulano@email.com amanhã às 10h sobre o projeto"*.
- **Consultas rápidas**: *"O que eu tenho na agenda hoje?"* ou *"Quanto já gastei de mercado este mês?"*.

> **Nota de desenvolvimento**: o projeto está sendo construído de forma incremental. A estrutura base, configuração e Docker estão prontos; os handlers do Telegram, agente Gemini e integrações Google estão sendo implementados por fases conforme o roadmap da ADR.

## Licença

MIT
