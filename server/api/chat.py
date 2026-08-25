from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from server.chat import run as runner
from server.chat import sse
from server.db import repo
from server.deps import State
from server.errors import ErrorBody, NotFound
from server.knowledge import capture
from server.models.stream import ChatRequest, StreamEnvelope

router = APIRouter(prefix="/api/chat", tags=["chat"])


SSE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "model": StreamEnvelope,
        "description": "An SSE stream. Each frame's `data` is one StreamEnvelope.",
        "content": {"text/event-stream": {}},
    },
    400: {"model": ErrorBody},
    404: {"model": ErrorBody},
    503: {"model": ErrorBody},
    507: {"model": ErrorBody, "description": "Not enough VRAM; the body carries the remedy."},
}


@router.post("/stream", responses=SSE_RESPONSES)
async def stream_chat(body: ChatRequest, state: State) -> EventSourceResponse:
    """Start a generation. The run outlives this response: closing the browser does not kill it."""
    prepared = await runner.prepare(state.db, state.registry, state.settings, body)
    live_run = state.live.start(prepared.run_id, prepared.message_id, prepared.conversation_id)
    queue: asyncio.Queue = asyncio.Queue(maxsize=2048)
    live_run.subscribers.add(queue)
    capture.register(state, prepared)
    return EventSourceResponse(sse.stream_new_run(prepared, queue))


@router.get("/runs/{run_id}/events", responses=SSE_RESPONSES)
async def resume_run(
    run_id: str,
    state: State,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Reattach to a run, live or finished, replaying exactly what this client has not seen."""
    return EventSourceResponse(sse.stream_resume(state.db, state.live, run_id, last_event_id))


class NudgeRequest(BaseModel):
    text: str


class NudgeResult(BaseModel):
    message_id: str
    token_idx: int
    """Where the interjection landed, so the transcript can mark the exact spot."""


@router.post("/runs/{run_id}/nudge")
async def nudge_run(run_id: str, body: NudgeRequest, state: State) -> NudgeResult:
    """Interrupt without starting over (BRIEF.md 4.4).

    This records the interjection and stops the run, keeping the partial. The client then streams
    a continuation with `continue_from` and `nudge` set - same machinery as editing and carrying
    on, which is exactly what a nudge is.
    """
    run = state.live.get(run_id)
    if run is None or run.finished:
        raise NotFound("Active run")
    landed = max(run.last_index + 1, 0)
    with state.db.session() as conn:
        repo.runs.add_nudge(conn, message_id=run.message_id, token_idx=landed, text=body.text)
    state.live.stop(run_id, "nudge")
    # Wait for the finaliser so the partial is on disk before the caller continues from it.
    with suppress(TimeoutError):
        await asyncio.wait_for(run.done.wait(), timeout=10)
    return NudgeResult(message_id=run.message_id, token_idx=landed)


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, state: State) -> dict[str, str]:
    """Esc: stop and keep. The partial text is already on disk."""
    if not state.live.stop(run_id, "user_stop"):
        raise NotFound("Active run")
    return {"status": "stopping"}
