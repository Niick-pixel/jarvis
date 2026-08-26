"""The approval queue as rows. The gate owns the decisions; this owns the reading and writing."""

from __future__ import annotations

import json
import sqlite3

from server.ids import now_ms
from server.models.tools import PendingCall
from server.tools import audit

SELECT = (
    "SELECT c.*, COALESCE(j.name, '') AS job_name FROM tool_calls c"
    " LEFT JOIN job_runs r ON r.id = c.job_run_id LEFT JOIN jobs j ON j.id = r.job_id"
)


def _call(row: sqlite3.Row) -> PendingCall:
    return PendingCall(
        id=row["id"],
        job_run_id=row["job_run_id"],
        job_name=row["job_name"],
        tool=row["tool"],
        target=row["target"],
        args_preview=audit.args_preview(json.loads(row["args_json"])),
        status=row["status"],
        delivered=bool(row["delivered"]),
        created_at=row["created_at"],
        decided_at=row["decided_at"],
        result=row["result"],
        error=row["error"],
    )


def get(conn: sqlite3.Connection, call_id: str) -> PendingCall | None:
    row = conn.execute(f"{SELECT} WHERE c.id = ?", (call_id,)).fetchone()
    return _call(row) if row else None


def args_for(conn: sqlite3.Connection, call_id: str) -> dict[str, object]:
    row = conn.execute("SELECT args_json FROM tool_calls WHERE id = ?", (call_id,)).fetchone()
    return dict(json.loads(row["args_json"])) if row else {}


def pending(conn: sqlite3.Connection) -> list[PendingCall]:
    rows = conn.execute(f"{SELECT} WHERE c.status = 'pending' ORDER BY c.created_at")
    return [_call(r) for r in rows]


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[PendingCall]:
    rows = conn.execute(f"{SELECT} ORDER BY c.created_at DESC LIMIT ?", (limit,))
    return [_call(r) for r in rows]


def for_run(conn: sqlite3.Connection, job_run_id: str) -> list[PendingCall]:
    rows = conn.execute(f"{SELECT} WHERE c.job_run_id = ? ORDER BY c.created_at", (job_run_id,))
    return [_call(r) for r in rows]


def mark_delivered(conn: sqlite3.Connection, call_ids: list[str]) -> None:
    conn.executemany(
        "UPDATE tool_calls SET delivered = 1 WHERE id = ?", [(cid,) for cid in call_ids]
    )


def expire_pending(conn: sqlite3.Connection, job_run_id: str, note: str) -> None:
    """Nobody decided in time. The call is denied, never quietly run (BRIEF.md 7)."""
    conn.execute(
        "UPDATE tool_calls SET status = 'denied', error = ?, decided_at = ?"
        " WHERE job_run_id = ? AND status = 'pending'",
        (note, now_ms(), job_run_id),
    )


def set_decision(conn: sqlite3.Connection, call_id: str, approved: bool) -> None:
    conn.execute(
        "UPDATE tool_calls SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
        ("approved" if approved else "denied", now_ms(), call_id),
    )
