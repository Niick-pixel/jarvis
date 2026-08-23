"""Editing the graph. Every write here adds a node; nothing is ever overwritten (BRIEF.md 4.1)."""

from __future__ import annotations

import json

from fastapi import APIRouter

from server.db import repo
from server.deps import State
from server.errors import NotFound
from server.graph import dag, merge
from server.models.message import Message, MessageEdit, SiblingSet

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("/{message_id}")
def get_message(message_id: str, state: State) -> Message:
    with state.db.session() as conn:
        message = repo.messages.get(conn, message_id)
    if message is None:
        raise NotFound("Message")
    return message


@router.patch("/{message_id}")
def edit_message(message_id: str, body: MessageEdit, state: State) -> Message:
    """Edit any message - including one the assistant wrote - by forking a sibling.

    The original is untouched and still reachable through the sibling switcher. This is the whole
    point of the project: steering by rewriting what the model said, then continuing from your
    version, which no hosted product will let you do.
    """
    with state.db.session() as conn:
        original = repo.messages.get(conn, message_id)
        if original is None:
            raise NotFound("Message")
        forked = repo.messages.create(
            conn,
            conversation_id=original.conversation_id,
            role=original.role,
            content=body.content,
            parent_id=original.parent_id,
            model_id=original.model_id,
            params=original.params,
            edited_from_id=original.id,
            forked_reason="edit",
        )
        repo.conversations.touch(conn, original.conversation_id, active_leaf_id=forked.id)
    return forked


@router.get("/{message_id}/siblings")
def siblings(message_id: str, state: State) -> SiblingSet:
    """Powers the inline `< 2/4 >` switcher."""
    with state.db.session() as conn:
        message = repo.messages.get(conn, message_id)
        if message is None:
            raise NotFound("Message")
        messages = repo.messages.list_for_conversation(conn, message.conversation_id)
    return dag.siblings(messages, message_id)


@router.post("/merge")
def merge_messages(body: merge.MergeRequest, state: State) -> Message:
    """Compose a new leaf from spans of sibling branches."""
    with state.db.session() as conn:
        sources: dict[str, Message] = {}
        for span in body.spans:
            if span.source_id in sources:
                continue
            found = repo.messages.get(conn, span.source_id)
            if found is None:
                raise NotFound(f"Message {span.source_id}")
            sources[span.source_id] = found

        result = merge.compose(body, sources)
        first = sources[body.spans[0].source_id]
        composed = repo.messages.create(
            conn,
            conversation_id=first.conversation_id,
            role=result.role,  # type: ignore[arg-type]
            content=result.content,
            parent_id=result.parent_id,
            edited_from_id=first.id,
            forked_reason="merge",
        )
        conn.execute(
            "UPDATE messages SET provenance_json = ? WHERE id = ?",
            (json.dumps([s.model_dump() for s in result.provenance]), composed.id),
        )
        repo.conversations.touch(conn, first.conversation_id, active_leaf_id=composed.id)
    return composed
