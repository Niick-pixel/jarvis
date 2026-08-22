from __future__ import annotations

import sqlite3

from server.ids import new_id, now_ms
from server.models.conversation import Conversation, ConversationCreate, ConversationUpdate

COLUMNS = (
    "id, title, project_id, active_leaf_id, system_prompt, visual_preset, created_at, updated_at"
)


def _row(row: sqlite3.Row) -> Conversation:
    return Conversation(**dict(row))


def create(conn: sqlite3.Connection, body: ConversationCreate) -> Conversation:
    ts = now_ms()
    cid = new_id("conv")
    conn.execute(
        "INSERT INTO conversations (id, title, system_prompt, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (cid, body.title, body.system_prompt, ts, ts),
    )
    got = get(conn, cid)
    assert got is not None
    return got


def get(conn: sqlite3.Connection, cid: str) -> Conversation | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM conversations WHERE id = ?", (cid,)).fetchone()
    return _row(row) if row else None


def list_all(conn: sqlite3.Connection, limit: int = 200) -> list[Conversation]:
    rows = conn.execute(
        f"SELECT {COLUMNS} FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,)
    )
    return [_row(r) for r in rows]


def update(conn: sqlite3.Connection, cid: str, body: ConversationUpdate) -> Conversation | None:
    fields = body.model_dump(exclude_none=True)
    if fields:
        assigns = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE conversations SET {assigns}, updated_at = ? WHERE id = ?",
            (*fields.values(), now_ms(), cid),
        )
    return get(conn, cid)


def touch(conn: sqlite3.Connection, cid: str, active_leaf_id: str | None = None) -> None:
    if active_leaf_id is None:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_ms(), cid))
    else:
        conn.execute(
            "UPDATE conversations SET updated_at = ?, active_leaf_id = ? WHERE id = ?",
            (now_ms(), active_leaf_id, cid),
        )


def delete(conn: sqlite3.Connection, cid: str) -> None:
    conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
