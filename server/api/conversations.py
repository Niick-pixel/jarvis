from __future__ import annotations

from fastapi import APIRouter

from server.db import repo
from server.deps import State
from server.errors import NotFound
from server.graph import dag
from server.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationTree,
    ConversationUpdate,
)
from server.models.message import Message, MessageCreate

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(state: State) -> list[Conversation]:
    with state.db.session() as conn:
        return repo.conversations.list_all(conn)


@router.post("")
def create_conversation(body: ConversationCreate, state: State) -> Conversation:
    with state.db.session() as conn:
        return repo.conversations.create(conn, body)


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
