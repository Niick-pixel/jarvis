"""SSE framing, including the resume path that makes a mid-answer refresh lossless.

Every token event carries `id: <run_id>:<index>`, so a reconnecting client sends `Last-Event-ID`
and gets exactly the tokens it missed - no duplicates, no gaps.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from server.chat.live import LiveRuns
from server.chat.run import PreparedRun, stored_assembly
from server.db import repo
from server.db.connection import Database
from server.errors import NotFound
from server.models.stream import (
    AssemblyEvent,
    DoneEvent,
    RunEvent,
    StopReason,
    StreamEvent,
    TokenEvent,
)

Payload = dict[str, Any]
Queue = "asyncio.Queue[StreamEvent | None]"


def payload(event: StreamEvent, run_id: str) -> Payload:
    body: Payload = {"event": event.type, "data": event.model_dump_json()}
    if isinstance(event, TokenEvent):
        body["id"] = f"{run_id}:{event.i}"
    return body


def parse_last_event_id(raw: str | None) -> int:
    """`run_abc:41` -> 41. Anything unparseable means "start from the beginning"."""
    if not raw or ":" not in raw:
        return -1
    try:
        return int(raw.rsplit(":", 1)[1])
    except ValueError:
        return -1


async def stream_new_run(
    prepared: PreparedRun, queue: asyncio.Queue[StreamEvent | None]
) -> AsyncIterator[Payload]:
    """The POST path. The caller subscribes before starting the task, so nothing is missed."""
    yield payload(AssemblyEvent(assembly=prepared.assembly), prepared.run_id)
    yield payload(
        RunEvent(
            run_id=prepared.run_id,
            message_id=prepared.message_id,
            seed=prepared.params.seed,
            model_id=prepared.model.id,
        ),
        prepared.run_id,
    )
    async for item in _drain(queue, prepared.run_id):
        yield item


async def stream_resume(
    db: Database, live: LiveRuns, run_id: str, last_event_id: str | None
) -> AsyncIterator[Payload]:
    row = _run_row(db, run_id)
    if row is None:
        raise NotFound("Run")
    after = parse_last_event_id(last_event_id)

    # Subscribe first: a token produced between the replay query and the subscription would
    # otherwise fall in the gap between them.
    subscription = live.subscribe(run_id)

    if assembly := stored_assembly(db, run_id):
        yield payload(AssemblyEvent(assembly=assembly), run_id)
    yield payload(
        RunEvent(
            run_id=run_id,
            message_id=row["message_id"],
            seed=row["seed"],
            model_id=row["model_id"],
        ),
        run_id,
    )

    highest = after
    with db.session() as conn:
        for event in repo.runs.tokens_after(conn, run_id, after):
            highest = max(highest, event.i)
            yield payload(event, run_id)

    if subscription is None:
        stop: StopReason = row["stop_reason"] or "eos"
        yield payload(DoneEvent(stop_reason=stop, message_id=row["message_id"]), run_id)
        return

    _, queue = subscription
    try:
        async for item in _drain(queue, run_id, skip_tokens_up_to=highest):
            yield item
    finally:
        live.unsubscribe(run_id, queue)


async def _drain(
    queue: asyncio.Queue[StreamEvent | None], run_id: str, *, skip_tokens_up_to: int = -1
) -> AsyncIterator[Payload]:
    while True:
        event = await queue.get()
        if event is None:
            return
        if isinstance(event, TokenEvent) and event.i <= skip_tokens_up_to:
            continue
        yield payload(event, run_id)
        if event.type == "done":
            return


def _run_row(db: Database, run_id: str) -> Any:
    with db.session() as conn:
        return conn.execute(
            "SELECT message_id, model_id, seed, stop_reason FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
