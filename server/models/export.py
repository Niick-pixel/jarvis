"""Conversations composting into notes (BRIEF.md 4.11)."""

from __future__ import annotations

from pydantic import BaseModel


class ExportResult(BaseModel):
    path: str
    """Where the note landed. Absolute, so you can open it without guessing."""
    bytes: int
    messages: int
    links: list[str] = []
    """The wikilinks written into it: the notes and files this conversation actually drew on."""
