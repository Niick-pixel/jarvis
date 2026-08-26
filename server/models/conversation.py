"""Conversations own a tree of messages and a pointer at the branch you are currently on."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from server.models.message import Message

VisualPreset = Literal["aurora", "solar", "deep"]


class Conversation(BaseModel):
    id: str
    title: str = ""
    project_id: str | None = None
    active_leaf_id: str | None = None
    system_prompt: str = ""
    visual_preset: VisualPreset = "aurora"
    created_at: int
    updated_at: int


class ConversationCreate(BaseModel):
    title: str = ""
    system_prompt: str = ""


class ConversationUpdate(BaseModel):
    title: str | None = None
    active_leaf_id: str | None = None
    system_prompt: str | None = None
    visual_preset: VisualPreset | None = None


class ConversationTree(BaseModel):
    """Every node in the conversation plus the currently active root-to-leaf path."""

    conversation: Conversation
    messages: list[Message]
    active_path: list[str]
