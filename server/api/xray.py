"""Token x-ray and deterministic replay (BRIEF.md 4.3, 4.5)."""

from __future__ import annotations

import json
import math

from fastapi import APIRouter

from server.db import repo
from server.deps import State
from server.errors import NotFound
from server.models.logprob import MessageTokens, NudgeMark, TokenView
from server.models.stream import Alternative

router = APIRouter(prefix="/api/messages", tags=["xray"])


@router.get("/{message_id}/tokens")
def message_tokens(message_id: str, state: State) -> MessageTokens:
    """Per-token probabilities for the tint layer and the alternatives popover.

    A backend that never reported logprobs yields an empty list and supports_logprobs=False, and
    the UI hides the x-ray for that message rather than showing a flat, meaningless tint.
    """
    with state.db.session() as conn:
        if repo.messages.get(conn, message_id) is None:
            raise NotFound("Message")
        run_id = repo.runs.latest_run_id(conn, message_id)
        rows = repo.runs.all_tokens(conn, run_id) if run_id else []
        marks = [
            NudgeMark(token_idx=n["token_idx"], text=n["text"], created_at=n["created_at"])
            for n in repo.runs.nudges_for(conn, message_id)
        ]

    tokens = [
        TokenView(
            idx=row["idx"],
            text=row["text"],
            logprob=row["logprob"],
            top=[Alternative(**a) for a in json.loads(row["top_json"])] if row["top_json"] else [],
            byte_start=row["byte_start"],
            byte_end=row["byte_end"],
            timing_ms=row["timing_ms"] or 0.0,
        )
        for row in rows
    ]
    scored = [t.logprob for t in tokens if t.logprob is not None]
    return MessageTokens(
        message_id=message_id,
        supports_logprobs=bool(scored),
        tokens=tokens,
        nudges=marks,
        mean_logprob=math.fsum(scored) / len(scored) if scored else None,
    )
