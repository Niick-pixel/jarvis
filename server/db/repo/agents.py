"""Jobs, their runs, and the inbox. Thin rows in, typed models out."""

from __future__ import annotations

import json
import sqlite3

from server.ids import new_id, now_ms
from server.models.agents import InboxItem, Job, JobCreate, JobPatch, JobRun, JobRunStatus


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        name=row["name"],
        cron=row["cron"],
        prompt=row["prompt"],
        tools=json.loads(row["tools"]),
        workspace=row["workspace"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        last_run_at=row["last_run_at"],
    )


def create_job(conn: sqlite3.Connection, body: JobCreate) -> Job:
    job_id = new_id("job")
    conn.execute(
        "INSERT INTO jobs (id, name, cron, prompt, tools, workspace, enabled, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (
            job_id,
            body.name,
            body.cron,
            body.prompt,
            json.dumps(body.tools),
            body.workspace,
            int(body.enabled),
            now_ms(),
        ),
    )
    got = get_job(conn, job_id)
    assert got is not None
    return got


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _job(row) if row else None


def list_jobs(conn: sqlite3.Connection) -> list[Job]:
    return [_job(r) for r in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")]


def patch_job(conn: sqlite3.Connection, job_id: str, body: JobPatch) -> Job | None:
    current = get_job(conn, job_id)
    if current is None:
        return None
    merged = current.model_copy(
        update={k: v for k, v in body.model_dump(exclude_none=True).items()}
    )
    conn.execute(
        "UPDATE jobs SET name = ?, cron = ?, prompt = ?, tools = ?, workspace = ?, enabled = ?"
        " WHERE id = ?",
        (
            merged.name,
            merged.cron,
            merged.prompt,
            json.dumps(merged.tools),
            merged.workspace,
            int(merged.enabled),
            job_id,
        ),
    )
    return get_job(conn, job_id)


def delete_job(conn: sqlite3.Connection, job_id: str) -> bool:
    return conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0


def start_run(conn: sqlite3.Connection, job_id: str, conversation_id: str | None) -> str:
    run_id = new_id("jrun")
    conn.execute(
        "INSERT INTO job_runs (id, job_id, conversation_id, status, started_at)"
        " VALUES (?,?,?, 'running', ?)",
        (run_id, job_id, conversation_id, now_ms()),
    )
    conn.execute("UPDATE jobs SET last_run_at = ? WHERE id = ?", (now_ms(), job_id))
    return run_id


def set_status(
    conn: sqlite3.Connection,
    run_id: str,
    status: JobRunStatus,
    *,
    summary: str = "",
    error: str = "",
    steps: int | None = None,
) -> None:
    finished = now_ms() if status in ("done", "failed", "cancelled") else None
    conn.execute(
        "UPDATE job_runs SET status = ?, finished_at = ?, summary = COALESCE(NULLIF(?,''),summary),"
        " error = COALESCE(NULLIF(?,''), error), steps = COALESCE(?, steps) WHERE id = ?",
        (status, finished, summary, error, steps, run_id),
    )


def _run(row: sqlite3.Row) -> JobRun:
    return JobRun(
        id=row["id"],
        job_id=row["job_id"],
        job_name=row["job_name"],
        conversation_id=row["conversation_id"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        steps=row["steps"],
        summary=row["summary"],
        error=row["error"],
    )


RUN_SELECT = "SELECT r.*, j.name AS job_name FROM job_runs r JOIN jobs j ON j.id = r.job_id"


def get_run(conn: sqlite3.Connection, run_id: str) -> JobRun | None:
    row = conn.execute(f"{RUN_SELECT} WHERE r.id = ?", (run_id,)).fetchone()
    return _run(row) if row else None


def list_runs(conn: sqlite3.Connection, job_id: str | None = None, limit: int = 50) -> list[JobRun]:
    if job_id:
        rows = conn.execute(
            f"{RUN_SELECT} WHERE r.job_id = ? ORDER BY r.started_at DESC LIMIT ?", (job_id, limit)
        )
    else:
        rows = conn.execute(f"{RUN_SELECT} ORDER BY r.started_at DESC LIMIT ?", (limit,))
    return [_run(r) for r in rows]


def stale_runs(conn: sqlite3.Connection) -> list[str]:
    """Runs left `running` by a restart: the task died with the process, so they cannot resume."""
    return [r["id"] for r in conn.execute("SELECT id FROM job_runs WHERE status = 'running'")]


def add_inbox(
    conn: sqlite3.Connection, *, job_run_id: str | None, title: str, body: str, flags: list[str]
) -> InboxItem:
    item_id = new_id("inb")
    conn.execute(
        "INSERT INTO inbox (id, created_at, job_run_id, title, body, flags) VALUES (?,?,?,?,?,?)",
        (item_id, now_ms(), job_run_id, title, body, json.dumps(flags)),
    )
    row = conn.execute("SELECT * FROM inbox WHERE id = ?", (item_id,)).fetchone()
    return _inbox(row)


def _inbox(row: sqlite3.Row) -> InboxItem:
    return InboxItem(
        id=row["id"],
        created_at=row["created_at"],
        job_run_id=row["job_run_id"],
        title=row["title"],
        body=row["body"],
        flags=json.loads(row["flags"]),
        read_at=row["read_at"],
    )


def list_inbox(conn: sqlite3.Connection, limit: int = 100) -> list[InboxItem]:
    rows = conn.execute("SELECT * FROM inbox ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_inbox(r) for r in rows]


def mark_read(conn: sqlite3.Connection, item_id: str, read: bool) -> InboxItem | None:
    conn.execute("UPDATE inbox SET read_at = ? WHERE id = ?", (now_ms() if read else None, item_id))
    row = conn.execute("SELECT * FROM inbox WHERE id = ?", (item_id,)).fetchone()
    return _inbox(row) if row else None
