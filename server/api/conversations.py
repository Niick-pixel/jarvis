from __future__ import annotations

from fastapi import APIRouter

from server.db import repo
from server.deps import State
from server.errors import NotFound
from server.graph import dag
from server.knowledge import export as export_mod
from server.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationTree,
    ConversationUpdate,
)
from server.models.export import ExportResult
from server.models.message import Message, MessageCreate
from server.tools import audit

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(state: State) -> list[Conversation]:
    with state.db.session() as conn:
        return repo.conversations.list_all(conn)


@router.post("")
def create_conversation(body: ConversationCreate, state: State) -> Conversation:
    with state.db.session() as conn:
        return repo.conversations.create(conn, body)


@router.post("/{conversation_id}/export")
def export_conversation(conversation_id: str, state: State) -> ExportResult:
    """The branch you are on, as a Markdown note in your vault (BRIEF.md 4.11)."""
    with state.db.session() as conn:
        result = export_mod.export(conn, conversation_id, state.settings.paths.vault_dir)
        if result is None:
            raise NotFound("Conversation")
        # An export writes to disk, so it belongs in the same log as everything else that does.
        audit.record(
            conn,
            actor="user",
            tool="export",
            outcome="ran",
            target=result.path,
            args={"conversation_id": conversation_id},
        )
        return result


@router.get("/{conversation_id}")
def get_tree(conversation_id: str, state: State) -> ConversationTree:
    with state.db.session() as conn:
        conversation = repo.conversations.get(conn, conversation_id)
        if conversation is None:
            raise NotFound("Conversation")
        messages = repo.messages.list_for_conversation(conn, conversation_id)
    path = dag.path_to_leaf(messages, conversation.active_leaf_id)
    return ConversationTree(
        conversation=conversation, messages=messages, active_path=[m.id for m in path]
    )


@router.patch("/{conversation_id}")
def update_conversation(
    conversation_id: str, body: ConversationUpdate, state: State
) -> Conversation:
    with state.db.session() as conn:
        updated = repo.conversations.update(conn, conversation_id, body)
    if updated is None:
        raise NotFound("Conversation")
    return updated


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, state: State) -> dict[str, str]:
    with state.db.session() as conn:
        repo.conversations.delete(conn, conversation_id)
    return {"status": "deleted"}


@router.post("/{conversation_id}/messages")
def add_message(conversation_id: str, body: MessageCreate, state: State) -> Message:
    with state.db.session() as conn:
        if repo.conversations.get(conn, conversation_id) is None:
            raise NotFound("Conversation")
        message = repo.messages.create(
            conn,
            conversation_id=conversation_id,
            role=body.role,
            content=body.content,
            parent_id=body.parent_id,
        )
        repo.conversations.touch(conn, conversation_id, active_leaf_id=message.id)
    return message
