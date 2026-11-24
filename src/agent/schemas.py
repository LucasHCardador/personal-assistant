"""Strict Pydantic schemas for agent inputs, media, and structured LLM outputs."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Normalized conversation turn stored in short-term memory."""

    role: Literal["user", "assistant"]
    content: str


class MediaAttachment(BaseModel):
    """Ephemeral in-memory media payload (never persisted to disk)."""

    kind: Literal["audio", "image"]
    mime_type: str
    data: bytes


class AssistantStructuredReply(BaseModel):
    """Strict structured output contract enforced across all LLM providers."""

    intent: Literal["chat", "clarification", "action_result", "error"] = Field(
        description="Semantic category of the assistant response."
    )
    summary: str = Field(
        min_length=1,
        description="Concise main response in Brazilian Portuguese.",
    )
    details: list[str] = Field(
        default_factory=list,
        description="Optional bullet points with extracted fields, totals, or steps.",
    )
    next_step_hint: str | None = Field(
        default=None,
        description="Optional short suggestion or follow-up question for the user.",
    )
