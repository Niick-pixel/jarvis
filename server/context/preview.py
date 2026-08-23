"""Assembling the context without generating, so the inspector is live before you press send.

Split out of chat/run.py, which owns turning a request into rows and tokens; this only answers
"what would go in".
"""

from __future__ import annotations

from server.chat.run import _resolve_ctx_len, resolve_model_id
from server.context.assembler import assemble
from server.db import repo
from server.db.connection import Database
from server.errors import NotFound
from server.models.context import ContextAssembly
from server.models.stream import ChatRequest
from server.providers.registry import ProviderRegistry
from server.settings import Settings


async def assemble_preview(
    db: Database,
    registry: ProviderRegistry,
    settings: Settings,
    *,
    conversation_id: str,
    parent_id: str | None,
    model_id: str | None,
    ctx_len: int | None,
    max_gen_tokens: int,
) -> ContextAssembly:
    """What would go into the next request, without making one."""
    from server.graph import dag

    resolved = await resolve_model_id(db, registry, settings, model_id)
    provider, model = await registry.resolve(resolved)
    with db.session() as conn:
        conversation = repo.conversations.get(conn, conversation_id)
        if conversation is None:
            raise NotFound("Conversation")
        messages = repo.messages.list_for_conversation(conn, conversation_id)
        leaf = parent_id or conversation.active_leaf_id
        path = dag.ancestors(messages, leaf) if leaf else []
        request = ChatRequest(conversation_id=conversation_id, ctx_len=ctx_len)
        return await assemble(
            conversation=conversation,
            path=path,
            provider=provider,
            model_id=model.id,
            ctx_len=_resolve_ctx_len(request, model, settings),
            max_gen_tokens=max_gen_tokens,
            prefs=repo.blocks.for_conversation(conn, conversation_id),
        )
