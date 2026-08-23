"""Composing a new leaf from spans of two sibling branches (BRIEF.md 4.1).

The client sends spans, never composed text. If it sent the text, the provenance we record would
be a claim rather than a fact - the server composes from the sources so the record is true by
construction.
"""

from __future__ import annotations

from pydantic import BaseModel

from server.errors import SovereignError
from server.models.message import Message


class MergeSpan(BaseModel):
    source_id: str
    start: int
    """Character offsets into the source message's content."""
    end: int


class MergeRequest(BaseModel):
    spans: list[MergeSpan]
    separator: str = ""


class MergeResult(BaseModel):
    content: str
    parent_id: str | None
    role: str
    provenance: list[MergeSpan]


def compose(request: MergeRequest, sources: dict[str, Message]) -> MergeResult:
    if not request.spans:
        raise SovereignError("invalid_request", "A merge needs at least one span.")

    parents = set()
    roles = set()
    pieces: list[str] = []
    for span in request.spans:
        source = sources.get(span.source_id)
        if source is None:
            raise SovereignError("not_found", f"Message {span.source_id} is not in this merge.")
        if not 0 <= span.start <= span.end <= len(source.content):
            raise SovereignError(
                "invalid_request",
                f"Span {span.start}:{span.end} does not fit message {span.source_id}, which is "
                f"{len(source.content)} characters.",
            )
        parents.add(source.parent_id)
        roles.add(source.role)
        pieces.append(source.content[span.start : span.end])

    if len(parents) > 1:
        raise SovereignError(
            "invalid_request",
            "Merge only composes sibling branches: every source must share one parent.",
        )
    if len(roles) > 1:
        raise SovereignError("invalid_request", "Merge sources must all have the same role.")

    return MergeResult(
        content=request.separator.join(pieces),
        parent_id=parents.pop(),
        role=roles.pop(),
        provenance=request.spans,
    )
