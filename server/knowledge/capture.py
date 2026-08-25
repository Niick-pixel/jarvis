"""Running a generation, then capturing what it taught us about the user.

Capture happens after the answer is finished and off the streaming path, so it never delays a
token. The client awaits the batch its own turn produced rather than polling, which is why the
task is registered by message id.
"""

from __future__ import annotations

import asyncio
import logging

from server.chat.execute import execute
from server.chat.run import PreparedRun
from server.db import repo
from server.deps import AppState
from server.graph import dag
from server.ids import new_id, now_ms
from server.knowledge import extract, memory, memory_git, memory_index
from server.models.memory import MemoryBatch, MemoryEntry

log = logging.getLogger(__name__)
MAX_TRACKED = 64


async def run_then_capture(state: AppState, prepared: PreparedRun) -> MemoryBatch:
    """The background task behind every generation: stream it, then learn from it.

    Returns the batch so the route can register this one task and the client can await it. An
    earlier version registered a second task *after* execute() returned, which raced the `done`
    event the client was waiting on - it could ask for its batch before the entry existed and be
    told, wrongly, that nothing was captured.
    """
    await execute(state.db, state.live, prepared)
    if not state.settings.memory.auto_extract:
        return MemoryBatch(batch_id="", entries=[])
    return await capture(state, prepared)


def register(state: AppState, prepared: PreparedRun) -> asyncio.Task[MemoryBatch]:
    _prune(state)
    task = asyncio.create_task(run_then_capture(state, prepared))
    state.extractions[prepared.message_id] = task
    return task


async def capture(state: AppState, prepared: PreparedRun) -> MemoryBatch:
    """Propose durable facts, write them as files, and return the batch so undo can target it."""
    batch_id = new_id("bat")
    try:
        with state.db.session() as conn:
            answer = repo.messages.get(conn, prepared.message_id)
            if answer is None or len(answer.content) < state.settings.memory.min_answer_chars:
                return MemoryBatch(batch_id=batch_id, entries=[])
            messages = repo.messages.list_for_conversation(conn, answer.conversation_id)
            path = dag.ancestors(messages, answer.id)
            question = next((m.content for m in reversed(path) if m.role == "user"), "")

        facts = await extract.propose(
            prepared.provider,
            model_id=prepared.model.id,
            ctx_len=prepared.ctx_len,
            question=question,
            answer=answer.content,
            limit=state.settings.memory.max_facts_per_turn,
        )
        if not facts:
            return MemoryBatch(batch_id=batch_id, entries=[])

        root = state.settings.paths.memory_dir
        # Facts recur across turns - "prefers short answers" surfaces again and again - so without
        # this the store silently fills with near-duplicates of the same thing.
        with state.db.session() as conn:
            known = {
                row["content_hash"]
                for row in conn.execute("SELECT content_hash FROM memory_entries")
            }
        written: list[MemoryEntry] = []
        for fact in facts:
            if memory.content_hash(fact) in known:
                continue
            known.add(memory.content_hash(fact))
            entry = MemoryEntry(
                id=new_id("mem"),
                path="",
                title=fact[:56],
                content=fact,
                source="auto",
                batch_id=batch_id,
                created_at=now_ms(),
                updated_at=now_ms(),
            )
            memory.write(root, entry)
            written.append(entry)

        if not written:
            return MemoryBatch(batch_id=batch_id, entries=[])

        memory_git.commit(root, f"memory: auto-captured {len(written)} from {prepared.message_id}")
        with state.db.session() as conn:
            memory_index.sync(conn, root)
            stored = memory_index.in_batch(conn, batch_id)
        return MemoryBatch(batch_id=batch_id, entries=stored)
    except Exception as exc:  # noqa: BLE001 - capture must never break the conversation
        log.warning("memory: capture failed: %s", exc)
        return MemoryBatch(batch_id=batch_id, entries=[])


def _prune(state: AppState) -> None:
    done = [key for key, task in state.extractions.items() if task.done()]
    for key in done[: max(0, len(state.extractions) - MAX_TRACKED)]:
        state.extractions.pop(key, None)
