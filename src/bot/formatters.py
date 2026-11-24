"""Deterministic HTML formatters for Telegram responses."""

import html

from src.agent.schemas import AssistantStructuredReply

_INTENT_PREFIX = {
    "chat": "💬",
    "clarification": "❓",
    "action_result": "✅",
    "error": "⚠️",
}


def format_structured_reply(reply: AssistantStructuredReply) -> str:
    """Render an AssistantStructuredReply into a consistent Telegram HTML message."""
    prefix = _INTENT_PREFIX.get(reply.intent, "💬")
    lines: list[str] = [f"{prefix} <b>{html.escape(reply.summary)}</b>"]

    if reply.details:
        lines.append("")
        for item in reply.details:
            lines.append(f"• {html.escape(item)}")

    if reply.next_step_hint:
        lines.append("")
        lines.append(f"<i>{html.escape(reply.next_step_hint)}</i>")

    return "\n".join(lines)


def format_welcome_message() -> str:
    """Return the deterministic /start welcome message."""
    return (
        "👋 <b>Assistente Pessoal conectado!</b>\n\n"
        "Você pode conversar comigo naturalmente por <b>texto</b>, <b>áudio</b> ou <b>foto</b>.\n\n"
        "<b>Comandos rápidos:</b>\n"
        "• /help — Ver exemplos de uso\n"
        "• /clear — Limpar histórico recente da conversa"
    )


def format_help_message() -> str:
    """Return the deterministic /help usage guide."""
    return (
        "📖 <b>Como usar no dia a dia</b>\n\n"
        "• <b>Texto livre:</b> envie gastos do carro, abastecimentos, mercado ou dúvidas.\n"
        "• <b>Áudio:</b> grave uma mensagem de voz ao sair do posto ou mercado.\n"
        "• <b>Foto:</b> envie foto de cupom fiscal ou do painel do carro.\n"
        "• <b>Desfazer:</b> use o botão <i>Desfazer</i> ou peça no chat para reverter o "
        "último lançamento.\n\n"
        "<i>As integrações com Google Calendar/Meet e lembretes proativos serão "
        "ativadas nas próximas fases.</i>"
    )
