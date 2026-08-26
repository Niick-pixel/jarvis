"""Memory entries (BRIEF.md 4.7). The files are the truth; these are their shape in transit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

MemoryScope = Literal["global", "project", "conversation"]
MemorySource = Literal["manual", "auto"]


class MemoryEntry(BaseModel):
    id: str
    path: str
    """Relative to ./memory/. This is a real file you can open, edit and delete."""
    scope: MemoryScope = "global"
    scope_ref: str | None = None
    title: str = ""
    content: str
    always: bool = False
    """Injected regardless of relevance - for the handful of facts that always matter."""
    source: MemorySource = "manual"
    batch_id: str | None = None
    """Groups one auto-extraction, so undo removes exactly what that pass wrote."""
    created_at: int = 0
    updated_at: int = 0
    retrieved_count: int = 0
    last_used_at: int | None = None


class MemoryCreate(BaseModel):
    title: str = ""
    content: str
    scope: MemoryScope = "global"
    scope_ref: str | None = None
    always: bool = False


class MemoryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    always: bool | None = None


class MemoryBatch(BaseModel):
    """What one auto-extraction wrote, so the UI can say 'saved 2 things' and offer undo."""

    batch_id: str
    entries: list[MemoryEntry]
