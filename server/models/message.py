"""Messages are nodes in a DAG, never rows in a scroll (BRIEF.md 4.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from server.models.params import SamplingParams

Role = Literal["system", "user", "assistant", "tool"]
MessageStatus = Literal["streaming", "complete", "stopped", "error"]
ForkReason = Literal["edit", "rerun", "forced_token", "merge", "nudge"]


class Message(BaseModel):
    id: str
    conversation_id: str
    parent_id: str | None = None
    role: Role
    content: str
    model_id: str | None = None
    params: SamplingParams | None = None
    token_count: int = 0
    status: MessageStatus = "complete"
    edited_from_id: str | None = None
    """Set when this node was forked from another; the original is never mutated."""
    forked_reason: ForkReason | None = None
    created_at: int


class MessageCreate(BaseModel):
    parent_id: str | None = None
    role: Role = "user"
    content: str


class MessageEdit(BaseModel):
    """Editing any message - including the assistant's own - forks a sibling."""

    content: str


class SiblingSet(BaseModel):
    """Powers the inline `< 2/4 >` switcher."""

    ids: list[str]
    index: int
