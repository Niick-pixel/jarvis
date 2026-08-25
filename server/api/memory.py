"""The Memory page (BRIEF.md 4.7): browse, edit, see history, and forget.

Every write goes to the Markdown file first and is then indexed, never the other way round. Delete
is a real delete - the file is removed and the index rebuilt, not flagged.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from server.deps import State
from server.errors import NotFound
from server.ids import new_id, now_ms
from server.knowledge import memory, memory_git, memory_index
from server.models.memory import MemoryBatch, MemoryCreate, MemoryEntry, MemoryUpdate

router = APIRouter(prefix="/api/memory", tags=["memory"])


class Commit(BaseModel):
    sha: str
    message: str
    when: str


class ForgetResult(BaseModel):
    forgotten: str
    remaining: int


@router.get("")
def list_memory(state: State) -> list[MemoryEntry]:
    with state.db.session() as conn:
        memory_index.sync(conn, state.settings.paths.memory_dir)
        return memory_index.list_all(conn)


@router.post("")
def create_memory(body: MemoryCreate, state: State) -> MemoryEntry:
    root = state.settings.paths.memory_dir
    entry = MemoryEntry(
        id=new_id("mem"),
        path="",
        title=body.title or body.content[:48],
        content=body.content,
        scope=body.scope,
        scope_ref=body.scope_ref,
        always=body.always,
        created_at=now_ms(),
        updated_at=now_ms(),
    )
    memory.write(root, entry)
    memory_git.commit(root, f"memory: add {entry.title}")
    with state.db.session() as conn:
        memory_index.sync(conn, root)
        stored = next((e for e in memory_index.list_all(conn) if e.id == entry.id), None)
    if stored is None:
        raise NotFound("Memory entry")
    return stored


@router.patch("/{entry_id}")
def update_memory(entry_id: str, body: MemoryUpdate, state: State) -> MemoryEntry:
    root = state.settings.paths.memory_dir
    with state.db.session() as conn:
        current = memory_index.get(conn, entry_id)
        if current is None:
            raise NotFound("Memory entry")
        updated = current.model_copy(
            update={
                "title": body.title if body.title is not None else current.title,
                "content": body.content if body.content is not None else current.content,
                "always": body.always if body.always is not None else current.always,
                "updated_at": now_ms(),
            }
        )
        # The title drives the filename, so replace rather than leave an orphan behind.
        memory.delete(root, current.path)
        memory.write(root, updated)
        memory_git.commit(root, f"memory: edit {updated.title}")
        memory_index.sync(conn, root)
        stored = memory_index.get(conn, entry_id)
    if stored is None:
        raise NotFound("Memory entry")
    return stored


@router.delete("/{entry_id}")
def forget(entry_id: str, state: State) -> ForgetResult:
    """Forget this: the file is deleted and the index rebuilt. Not a tombstone."""
    root = state.settings.paths.memory_dir
    with state.db.session() as conn:
        entry = memory_index.get(conn, entry_id)
        if entry is None:
            raise NotFound("Memory entry")
        memory.delete(root, entry.path)
        memory_git.commit(root, f"memory: forget {entry.title}")
        remaining = memory_index.sync(conn, root)
    return ForgetResult(forgotten=entry.title, remaining=remaining)


@router.get("/batches/for-message/{message_id}")
async def batch_for_message(message_id: str, state: State) -> MemoryBatch:
    """Wait for the capture this message triggered, and report what it wrote.

    Awaiting the task beats polling: the client asked the question, so it can wait for the answer
    rather than guessing when to look. An empty batch means nothing durable was found.
    """
    task = state.extractions.get(message_id)
    if task is None:
        return MemoryBatch(batch_id="", entries=[])
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=45)
    except TimeoutError:
        return MemoryBatch(batch_id="", entries=[])


@router.delete("/batches/{batch_id}")
def undo_batch(batch_id: str, state: State) -> ForgetResult:
    """Undo one automatic capture: deletes exactly the files that batch wrote."""
    root = state.settings.paths.memory_dir
    with state.db.session() as conn:
        entries = memory_index.in_batch(conn, batch_id)
        if not entries:
            raise NotFound("Memory batch")
        for entry in entries:
            memory.delete(root, entry.path)
        memory_git.commit(root, f"memory: undo automatic capture {batch_id}")
        remaining = memory_index.sync(conn, root)
    return ForgetResult(forgotten=f"{len(entries)} auto-captured", remaining=remaining)


@router.get("/{entry_id}/history")
def history(entry_id: str, state: State) -> list[Commit]:
    with state.db.session() as conn:
        entry = memory_index.get(conn, entry_id)
    if entry is None:
        raise NotFound("Memory entry")
    return [Commit(**c) for c in memory_git.history(state.settings.paths.memory_dir, entry.path)]
