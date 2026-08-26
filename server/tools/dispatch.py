"""What happens to a call once the gate has ruled: it becomes a row, and sometimes it runs.

Split out of `gate.py`, which owns the two rules - provenance and approval. This owns the
bookkeeping those rules produce: the queue row, the execution, and the audit line for each.
"""

from __future__ import annotations

import json
import sqlite3

from server.ids import new_id, now_ms
from server.tools import audit
from server.tools.builtin import ToolContext, ToolResult
from server.tools.gate import Planned
from server.tools.sandbox import Denied


def enqueue(conn: sqlite3.Connection, planned: Planned, job_run_id: str | None) -> str:
    """Park a call at the gate. The real arguments are stored because they have to be run later."""
    call_id = new_id("tcl")
    conn.execute(
        "INSERT INTO tool_calls (id, job_run_id, tool, args_json, target, status, created_at)"
        " VALUES (?,?,?,?,?, 'pending', ?)",
        (
            call_id,
            job_run_id,
            planned.call.tool,
            json.dumps(planned.call.args),
            planned.target,
            now_ms(),
        ),
    )
    audit.record(
        conn,
        actor=_actor_for(conn, job_run_id),
        tool=planned.call.tool,
        outcome="awaiting_approval",
        target=planned.target,
        args=planned.call.args,
    )
    return call_id


async def execute(
    conn: sqlite3.Connection,
    planned: Planned,
    ctx: ToolContext,
    *,
    actor: str,
    job_run_id: str | None = None,
    call_id: str | None = None,
) -> ToolResult:
    """Run one approved or unGated call, record it, and return its result. Never raises."""
    assert planned.tool is not None
    row_id = call_id or clear(conn, planned, job_run_id)
    try:
        result = await planned.tool.run(ctx, planned.call.args)
    except (Denied, OSError, ValueError) as exc:
        conn.execute(
            "UPDATE tool_calls SET status = 'failed', error = ?, decided_at = ? WHERE id = ?",
            (str(exc), now_ms(), row_id),
        )
        audit.record(
            conn,
            actor=actor,
            tool=planned.call.tool,
            outcome="refused" if isinstance(exc, Denied) else "failed",
            target=planned.target,
            args=planned.call.args,
            note=str(exc)[:200],
        )
        return ToolResult(output=f"{planned.call.tool} failed: {exc}", target=planned.target)
    conn.execute(
        "UPDATE tool_calls SET status = 'ran', result = ?, decided_at = ? WHERE id = ?",
        (result.output[:400], now_ms(), row_id),
    )
    audit.record(
        conn,
        actor=actor,
        tool=planned.call.tool,
        outcome="ran",
        target=result.target,
        args=planned.call.args,
        result=result.output,
    )
    return result


def clear(conn: sqlite3.Connection, planned: Planned, job_run_id: str | None) -> str:
    """A call that does not need you: a read inside the sandbox, or one you already granted."""
    call_id = new_id("tcl")
    conn.execute(
        "INSERT INTO tool_calls (id, job_run_id, tool, args_json, target, status, created_at)"
        " VALUES (?,?,?,?,?, 'approved', ?)",
        (
            call_id,
            job_run_id,
            planned.call.tool,
            json.dumps(planned.call.args),
            planned.target,
            now_ms(),
        ),
    )
    return call_id


def record_refusal(
    conn: sqlite3.Connection, planned: Planned, job_run_id: str | None, actor: str
) -> str:
    """A call the job was never allowed to make. A row too, so the transcript shows what and why."""
    call_id = new_id("tcl")
    conn.execute(
        "INSERT INTO tool_calls (id, job_run_id, tool, args_json, target, status, created_at,"
        " decided_at, error) VALUES (?,?,?,?,?, 'denied', ?,?,?)",
        (
            call_id,
            job_run_id,
            planned.call.tool,
            json.dumps(planned.call.args),
            planned.target,
            now_ms(),
            now_ms(),
            planned.refusal,
        ),
    )
    audit.record(
        conn,
        actor=actor,
        tool=planned.call.tool,
        outcome="refused",
        target=planned.target,
        args=planned.call.args,
        note=planned.refusal,
    )
    return call_id


def _actor_for(conn: sqlite3.Connection, job_run_id: str | None) -> str:
    if job_run_id is None:
        return "user"
    row = conn.execute(
        "SELECT j.name AS name FROM job_runs r JOIN jobs j ON j.id = r.job_id WHERE r.id = ?",
        (job_run_id,),
    ).fetchone()
    return f"job:{row['name']}" if row else "job"
