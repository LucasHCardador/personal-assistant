# Personal Assistant — Documentação

Bem-vindo ao portal de documentação do **Personal Assistant**, um assistente pessoal self-hosted conectado ao **Telegram**, com inteligência multimodal configurável (padrão gratuito via **Gemini Free Tier**) e integrado ao **ecossistema Google** (Calendar, Meet e Sheets).

## Visão Rápida

- **Interface no Telegram**: envie texto, áudio ou fotos (cupons fiscais, painel do carro).
- **Multi-Provedor de IA**: suporte a **Gemini** (padrão gratuito e multimodal), **Claude (Anthropic)** e provedores **OpenAI-compatible** (OpenRouter `:free`, Groq, Ollama).
- **Saídas Estruturadas**: validação estrita com Pydantic + templates determinísticos para respostas consistentes.
- **Governança de Dados**: processamento de mídia em memória (`BytesIO`) com descarte imediato e limpeza periódica de histórico local.

## Navegação

- **Fases do Projeto**: acompanhamento detalhado do que foi entregue em cada fase de desenvolvimento.
- **Arquitetura (ADRs)**: decisões técnicas, diagramas e roadmap em [ADR-001](research/adr-001-arquitetura-e-viabilizacao.md).
