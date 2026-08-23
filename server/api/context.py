"""The Context Inspector's endpoints: see what will go in, and change it before it does."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from server.chat.run import assemble_preview
from server.db import repo
from server.db.repo.blocks import BlockPref
from server.deps import State
from server.errors import NotFound
from server.models.context import ContextAssembly

router = APIRouter(prefix="/api/context", tags=["context"])


class PreviewRequest(BaseModel):
    conversation_id: str
    parent_id: str | None = None
    model_id: str | None = None
    ctx_len: int | None = None
    max_gen_tokens: int = 2048


@router.post("/preview")
async def preview(body: PreviewRequest, state: State) -> ContextAssembly:
    """Assemble without generating, so the bar under the composer is live before you send."""
    return await assemble_preview(
        state.db,
        state.registry,
        state.settings,
        conversation_id=body.conversation_id,
        parent_id=body.parent_id,
        model_id=body.model_id,
        ctx_len=body.ctx_len,
        max_gen_tokens=body.max_gen_tokens,
    )


class PrefsUpdate(BaseModel):
    conversation_id: str
    prefs: list[BlockPref]


@router.patch("/blocks")
def update_prefs(body: PrefsUpdate, state: State) -> list[BlockPref]:
    """Pin, disable or reorder blocks. Preferences outlive the request that set them."""
    with state.db.session() as conn:
        if repo.conversations.get(conn, body.conversation_id) is None:
            raise NotFound("Conversation")
        for pref in body.prefs:
            repo.blocks.put(conn, body.conversation_id, pref)
        return list(repo.blocks.for_conversation(conn, body.conversation_id).values())
