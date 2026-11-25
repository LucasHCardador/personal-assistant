"""Deterministic HTML formatters for Telegram responses."""

import html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.agent.schemas import AssistantStructuredReply
from src.storage.database import ReminderRecord

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

    for section in reply.sections:
        if not section.items:
            continue
        lines.append("")
        lines.append(f"<b>{html.escape(section.title)}</b>")
        for item in section.items:
            lines.append(f"• {html.escape(item)}")

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
        "• <b>Texto livre:</b> envie gastos do carro, abastecimentos, mercado, compromissos "
        "ou lembretes.\n"
        "• <b>Áudio:</b> grave uma mensagem de voz ao sair do posto, mercado ou consulta.\n"
        "• <b>Foto:</b> envie foto de cupom fiscal ou do painel do carro.\n"
        "• <b>Agenda e Meet:</b> agende compromissos e gere links do Google Meet com "
        "confirmação rápida por botões.\n"
        "• <b>Lembretes proativos:</b> crie lembretes únicos ou recorrentes e receba o resumo "
        "matinal diário.\n"
        "• <b>Desfazer:</b> use o botão <i>Desfazer</i> ou peça no chat para reverter o "
        "último lançamento."
    )


_RECURRENCE_LABELS = {
    "daily": "Diário",
    "weekly": "Semanal",
    "monthly": "Mensal",
}


def _format_local_time(iso_str: str, timezone_name: str) -> str:
    """Format an ISO-8601 timestamp as local HH:MM (or 'Dia todo' for date-only values)."""
    if not iso_str:
        return "--:--"
    if "T" not in iso_str:
        return "Dia todo"
    parsed = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    tz = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz).strftime("%H:%M")


def format_morning_summary(
    *,
    date_label: str,
    events: list[dict[str, Any]],
    reminders: list[ReminderRecord],
    maintenance_items: list[dict[str, Any]],
    timezone_name: str,
) -> str:
    """Render the daily morning summary as deterministic Telegram HTML."""
    lines: list[str] = [f"<b>Resumo Matinal — {html.escape(date_label)}</b>", ""]

    lines.append("<b>Agenda de hoje</b>")
    if events:
        for event in events:
            time_str = _format_local_time(str(event.get("start", "")), timezone_name)
            summary = html.escape(str(event.get("summary") or "(Sem título)"))
            entry = f"• {html.escape(time_str)} — {summary}"
            meet_link = str(event.get("meet_link") or "").strip()
            if meet_link:
                entry += f" (<a href=\"{html.escape(meet_link, quote=True)}\">Meet</a>)"
            lines.append(entry)
    else:
        lines.append("• Nenhum compromisso agendado.")

    lines.append("")
    lines.append("<b>Lembretes do dia</b>")
    if reminders:
        for reminder in reminders:
            time_str = _format_local_time(reminder.trigger_at, timezone_name)
            lines.append(f"• {html.escape(time_str)} — {html.escape(reminder.title)}")
    else:
        lines.append("• Nenhum lembrete pendente para hoje.")

    if maintenance_items:
        lines.append("")
        lines.append("<b>Manutenção do carro</b>")
        for item in maintenance_items:
            name = html.escape(str(item.get("item", "")))
            status = html.escape(str(item.get("status", "")))
            lines.append(f"• {name} — <i>{status}</i>")

    return "\n".join(lines)


def format_event_alert(
    *,
    event: dict[str, Any],
    window_label: str,
    timezone_name: str,
) -> str:
    """Render an upcoming calendar event alert as deterministic Telegram HTML."""
    summary = html.escape(str(event.get("summary") or "(Sem título)"))
    start_str = str(event.get("start") or "")
    time_str = _format_local_time(start_str, timezone_name)
    lines: list[str] = [
        f"<b>Lembrete de Compromisso ({html.escape(window_label)})</b>",
        "",
        f"• <b>{summary}</b> às {html.escape(time_str)}",
    ]

    location = str(event.get("location") or "").strip()
    if location:
        lines.append(f"• Local: {html.escape(location)}")

    meet_link = str(event.get("meet_link") or "").strip()
    if meet_link:
        lines.append(f"• Google Meet: <a href=\"{html.escape(meet_link, quote=True)}\">Entrar</a>")

    return "\n".join(lines)


def format_maintenance_alert(
    *,
    items: list[dict[str, Any]],
    current_km: int | None,
) -> str:
    """Render a vehicle maintenance alert as deterministic Telegram HTML."""
    lines: list[str] = ["<b>Alerta de Manutenção do Carro</b>"]
    if current_km is not None:
        lines.append(f"Quilometragem atual: <b>{current_km} km</b>")
    lines.append("")

    for item in items:
        name = html.escape(str(item.get("item", "")))
        status = html.escape(str(item.get("status", "")))
        lines.append(f"• <b>{name}</b>: {status}")

    return "\n".join(lines)


def format_reminder_notification(
    *,
    reminder: ReminderRecord,
    timezone_name: str,
) -> str:
    """Render a triggered reminder notification as deterministic Telegram HTML."""
    time_str = _format_local_time(reminder.trigger_at, timezone_name)
    lines: list[str] = [
        "<b>Lembrete</b>",
        "",
        f"• {html.escape(reminder.title)} ({html.escape(time_str)})",
    ]
    if reminder.recurrence in _RECURRENCE_LABELS:
        rec_label = _RECURRENCE_LABELS[reminder.recurrence]
        lines.append(f"<i>Recorrência: {html.escape(rec_label)}</i>")

    return "\n".join(lines)


def _format_local_datetime(iso_value: str, timezone_name: str) -> str:
    """Format an ISO-8601 string into DD/MM HH:MM in the configured timezone."""
    if not iso_value:
        return ""
    try:
        if "T" not in iso_value:
            dt_only = datetime.strptime(iso_value, "%Y-%m-%d")
            return f"{dt_only.strftime('%d/%m')} (dia todo)"
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(timezone_name))
        return dt.astimezone(ZoneInfo(timezone_name)).strftime("%d/%m às %H:%M")
    except ValueError:
        return iso_value


def format_weekly_summary(
    *,
    period_label: str,
    events: list[dict[str, Any]],
    reminders: list[ReminderRecord],
    maintenance_items: list[dict[str, Any]],
    timezone_name: str,
) -> str:
    """Render the weekly overview as deterministic Telegram HTML."""
    lines: list[str] = [f"<b>Resumo da Semana ({html.escape(period_label)})</b>", ""]

    lines.append("<b>Compromissos dos próximos 7 dias:</b>")
    if events:
        for ev in events:
            when = _format_local_datetime(str(ev.get("start") or ""), timezone_name)
            summary = html.escape(str(ev.get("summary") or "Sem título"))
            lines.append(f"• {html.escape(when)} — {summary}")
    else:
        lines.append("• Nenhum compromisso agendado para os próximos 7 dias.")

    lines.append("")
    lines.append("<b>Lembretes pendentes:</b>")
    if reminders:
        for rem in reminders:
            when = _format_local_datetime(rem.trigger_at, timezone_name)
            lines.append(f"• {html.escape(when)} — {html.escape(rem.title)}")
    else:
        lines.append("• Nenhum lembrete pendente para a semana.")

    if maintenance_items:
        lines.append("")
        lines.append("<b>Manutenções do carro em atenção:</b>")
        for item in maintenance_items:
            name = html.escape(str(item.get("item", "")))
            status = html.escape(str(item.get("status", "")))
            lines.append(f"• {name}: {status}")

    return "\n".join(lines)
