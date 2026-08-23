"""How a request forks off an existing message: continue, force a token, or replay.

All three are the same move underneath - take an existing message, decide how much of its text to
keep, and generate a sibling from there. Nothing here mutates an original.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from server.db import repo
from server.errors import NotFound, SovereignError
from server.models.message import ForkReason, Message
from server.models.params import SamplingParams
from server.models.stream import ChatRequest, ForceToken


@dataclass
class Steering:
    """How this request forks off an existing message, if it does."""

    prefix: str | None = None
    source_id: str | None = None
    parent_id: str | None = None
    reason: ForkReason | None = None
    params: SamplingParams | None = None


def resolve_steering(conn: sqlite3.Connection, request: ChatRequest) -> Steering:
    """Turn continue / force-token / rerun into a prefix, a parent and a fork reason.

    All three are the same move underneath: take an existing message, decide how much of its text
    to keep, and generate a sibling from there. Nothing mutates the original.
    """
    if request.force_token:
        return _forced_token(conn, request.force_token)
    if request.continue_from:
        source = _require(conn, request.continue_from, "Message to continue")
        reason: ForkReason = "nudge" if request.nudge else "edit"
        return Steering(
            prefix=source.content,
            source_id=source.id,
            parent_id=source.parent_id,
            reason=reason,
        )
    if request.rerun_of:
        source = _require(conn, request.rerun_of, "Message to rerun")
        return Steering(
            source_id=source.id,
            parent_id=source.parent_id,
            reason="rerun",
            params=_recorded_params(conn, source.id, request),
        )
    return Steering()


def _require(conn: sqlite3.Connection, message_id: str, what: str) -> Message:
    found = repo.messages.get(conn, message_id)
    if found is None:
        raise NotFound(what)
    return found


def _forced_token(conn: sqlite3.Connection, forced: ForceToken) -> Steering:
    """Truncate at the chosen token's byte offset and put a different token in its place."""
    source = _require(conn, forced.message_id, "Message to steer")
    run_id = repo.runs.latest_run_id(conn, source.id)
    start = repo.runs.byte_start(conn, run_id, forced.token_idx) if run_id else None
    if start is None:
        raise SovereignError(
            "not_found",
            "No stored token log for that message, so it cannot be steered at the token level.",
            status_code=404,
        )
    head = source.content.encode()[:start].decode(errors="ignore")
    return Steering(
        prefix=head + forced.token,
        source_id=source.id,
        parent_id=source.parent_id,
        reason="forced_token",
    )


def _recorded_params(
    conn: sqlite3.Connection, message_id: str, request: ChatRequest
) -> SamplingParams:
    """Replay uses the params actually recorded, so the same seed reproduces the same output.

    Anything the client set explicitly still wins - that is "rerun with...", which is meant to
    differ.
    """
    row = repo.runs.params_for(conn, message_id)
    if row is None:
        return request.params.resolved()
    recorded = SamplingParams(
        seed=row["seed"],
        temperature=row["temperature"],
        top_p=row["top_p"],
        top_k=row["top_k"],
        repeat_penalty=row["repeat_penalty"],
        max_tokens=request.params.max_tokens,
        n_probs=request.params.n_probs,
    )
    overrides = {k: getattr(request.params, k) for k in request.params.model_fields_set}
    return recorded.model_copy(update=overrides)
