"""The Council's endpoints (BRIEF.md 4.6)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from server.council import run as council_run
from server.council import scoreboard
from server.deps import State
from server.errors import NotFound
from server.models.council import (
    AgreementCell,
    CouncilAnswer,
    CouncilEnvelope,
    CouncilReport,
    CouncilRequest,
    CouncilVerdict,
    Ranking,
    ScoreboardRow,
)

router = APIRouter(prefix="/api/council", tags=["council"])

SSE_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "model": CouncilEnvelope,
        "description": "An SSE stream. Each frame's `data` is one CouncilEnvelope.",
        "content": {"text/event-stream": {}},
    }
}


@router.post("/run", responses=SSE_RESPONSES)
async def start(body: CouncilRequest, state: State) -> EventSourceResponse:
    async def stream() -> AsyncIterator[dict[str, Any]]:
        async for event in council_run.run(state.db, state.registry, state.settings, body):
            yield {"event": event.type, "data": event.model_dump_json()}

    return EventSourceResponse(stream())


@router.get("/scoreboard")
def read_scoreboard(state: State) -> list[ScoreboardRow]:
    with state.db.session() as conn:
        return scoreboard.read(conn)


@router.get("/runs/{run_id}")
def read_run(run_id: str, state: State) -> CouncilReport:
    """Read a finished council back, including who actually wrote which labelled answer."""
    with state.db.session() as conn:
        head = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
        if head is None:
            raise NotFound("Council run")
        answers = [
            CouncilAnswer(
                label=r["label"],
                model_id=r["model_id"],
                content=r["content"],
                gen_tokens=r["gen_tokens"],
                gen_ms=r["gen_ms"],
                error=r["error"],
            )
            for r in conn.execute(
                "SELECT * FROM council_answers WHERE run_id = ? ORDER BY ord", (run_id,)
            )
        ]
        cells = [
            AgreementCell(a=r["a_label"], b=r["b_label"], similarity=r["similarity"])
            for r in conn.execute("SELECT * FROM council_agreement WHERE run_id = ?", (run_id,))
        ]
        ranking = [
            Ranking(label=r["label"], rank=r["rank"], reason=r["reason"])
            for r in conn.execute(
                "SELECT * FROM council_ranking WHERE run_id = ? ORDER BY rank", (run_id,)
            )
        ]

    return CouncilReport(
        run_id=run_id,
        question=head["question"],
        mode=head["mode"],
        answers=answers,
        agreement=cells,
        verdict=CouncilVerdict(
            ranking=ranking,
            synthesis=head["synthesis"],
            disagreements=head["disagreements"],
            judge_model_id=head["judge_model_id"],
        ),
    )
