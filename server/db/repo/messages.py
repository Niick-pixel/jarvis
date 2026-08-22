from __future__ import annotations

import json
import sqlite3

from server.ids import new_id, now_ms
from server.models.message import ForkReason, Message, MessageStatus, Role
from server.models.params import SamplingParams

COLUMNS = (
    "id, conversation_id, parent_id, role, content, model_id, params_json, token_count,"
    " status, edited_from_id, forked_reason, created_at"
)


def _row(row: sqlite3.Row) -> Message:
    data = dict(row)
    raw = data.pop("params_json", None)
    data["params"] = SamplingParams(**json.loads(raw)) if raw else None
    return Message(**data)


def create(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    role: Role,
    content: str,
    parent_id: str | None = None,
    model_id: str | None = None,
    params: SamplingParams | None = None,
    token_count: int = 0,
    status: MessageStatus = "complete",
    edited_from_id: str | None = None,
    forked_reason: ForkReason | None = None,
) -> Message:
    mid = new_id("msg")
    conn.execute(
        "INSERT INTO messages (id, conversation_id, parent_id, role, content, model_id,"
        " params_json, token_count, status, edited_from_id, forked_reason, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            mid,
            conversation_id,
            parent_id,
            role,
            content,
            model_id,
            json.dumps(params.model_dump()) if params else None,
            token_count,
            status,
            edited_from_id,
            forked_reason,
            now_ms(),
        ),
    )
    got = get(conn, mid)
    assert got is not None
    return got


def get(conn: sqlite3.Connection, mid: str) -> Message | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM messages WHERE id = ?", (mid,)).fetchone()
    return _row(row) if row else None


def list_for_conversation(conn: sqlite3.Connection, cid: str) -> list[Message]:
    rows = conn.execute(
        f"SELECT {COLUMNS} FROM messages WHERE conversation_id = ? ORDER BY created_at, id", (cid,)
    )
    return [_row(r) for r in rows]


def append_content(conn: sqlite3.Connection, mid: str, text: str) -> None:
    """Streaming writes land in the row itself, so a crash leaves the partial on disk."""
    conn.execute("UPDATE messages SET content = content || ? WHERE id = ?", (text, mid))


def finish(
    conn: sqlite3.Connection, mid: str, *, status: MessageStatus, token_count: int | None = None
) -> None:
    if token_count is None:
        conn.execute("UPDATE messages SET status = ? WHERE id = ?", (status, mid))
    else:
        conn.execute(
            "UPDATE messages SET status = ?, token_count = ? WHERE id = ?",
            (status, token_count, mid),
        )
