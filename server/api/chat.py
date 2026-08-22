from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Header
from sse_starlette.sse import EventSourceResponse

from server.chat import execute as executor
from server.chat import run as runner
from server.chat import sse
from server.deps import State
from server.errors import ErrorBody, NotFound
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
    asyncio.create_task(executor.execute(state.db, state.live, prepared))
    return EventSourceResponse(sse.stream_new_run(prepared, queue))


@router.get("/runs/{run_id}/events", responses=SSE_RESPONSES)
async def resume_run(
    run_id: str,
    state: State,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Reattach to a run, live or finished, replaying exactly what this client has not seen."""
    return EventSourceResponse(sse.stream_resume(state.db, state.live, run_id, last_event_id))


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, state: State) -> dict[str, str]:
    """Esc: stop and keep. The partial text is already on disk."""
    if not state.live.stop(run_id, "user_stop"):
        raise NotFound("Active run")
    return {"status": "stopping"}
