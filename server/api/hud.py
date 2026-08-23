from __future__ import annotations

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from server.deps import State
from server.hud import counters, telemetry
from server.models.hud import LifetimeCounters

router = APIRouter(prefix="/api/hud", tags=["hud"])


@router.get("/stream")
async def hud_stream(state: State) -> EventSourceResponse:
    return EventSourceResponse(telemetry.stream(state.live))


@router.get("/counters")
def hud_counters(state: State) -> LifetimeCounters:
    with state.db.session() as conn:
        return counters.read(conn)
