from __future__ import annotations

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from server.deps import State
from server.hud import counters, telemetry
from server.models.hud import HudSample, LifetimeCounters

router = APIRouter(prefix="/api/hud", tags=["hud"])


# Declared so the sample shape reaches the OpenAPI schema and therefore the generated
# TypeScript. Without it the HUD would be the one part of the API the frontend types by hand.
HUD_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "model": HudSample,
        "description": "An SSE stream of 1 Hz samples.",
        "content": {"text/event-stream": {}},
    }
}


@router.get("/stream", responses=HUD_RESPONSES)
async def hud_stream(state: State) -> EventSourceResponse:
    return EventSourceResponse(telemetry.stream(state.live))


@router.get("/counters")
def hud_counters(state: State) -> LifetimeCounters:
    with state.db.session() as conn:
        return counters.read(conn)
