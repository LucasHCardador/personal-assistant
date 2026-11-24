"""Strict Pydantic schemas for agent inputs, media, and structured LLM outputs."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-agnostic declaration of an executable tool."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


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
    media_summary: str | None = Field(
        default=None,
        description=(
            "Factual summary of what the user said in audio or showed in an image, "
            "when media was attached."
        ),
    )

    _undo_action_id: int | None = PrivateAttr(default=None)
    _pending_confirmation_id: int | None = PrivateAttr(default=None)

    @property
    def undo_action_id(self) -> int | None:
        """Internal action_history ID when this reply recorded an undoable write."""
        return self._undo_action_id

    def set_undo_action_id(self, action_id: int | None) -> None:
        """Attach an internal action_history ID without altering the JSON schema."""
        self._undo_action_id = action_id

    @property
    def pending_confirmation_id(self) -> int | None:
        """Internal pending_confirmations ID when this reply awaits inline confirmation."""
        return self._pending_confirmation_id

    def set_pending_confirmation_id(self, confirmation_id: int | None) -> None:
        """Attach an internal pending_confirmations ID without altering the JSON schema."""
        self._pending_confirmation_id = confirmation_id
