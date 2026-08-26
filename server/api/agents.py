"""Scheduled jobs, their runs, and the inbox they report into (BRIEF.md 4.9)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from server.agents import loop, scheduler
from server.db import repo
from server.deps import State
from server.errors import NotFound, SovereignError
from server.models.agents import InboxItem, Job, JobCreate, JobPatch, JobRun
from server.models.tools import PendingCall

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _runtime(state: State) -> loop.Runtime:
    return loop.Runtime(state.db, state.registry, state.settings, state.live, state.approvals)


def _check_cron(expression: str) -> None:
    problem = scheduler.validate_cron(expression)
    if problem:
        raise SovereignError("invalid_request", f"That is not a cron expression: {problem}")


@router.get("/jobs")
def list_jobs(state: State) -> list[Job]:
    with state.db.session() as conn:
        jobs = repo.agents.list_jobs(conn)
    return [state.scheduler.decorate(j) for j in jobs] if state.scheduler else jobs


@router.post("/jobs")
def create_job(body: JobCreate, state: State) -> Job:
    _check_cron(body.cron)
    with state.db.session() as conn:
        job = repo.agents.create_job(conn, body)
    if state.scheduler:
        state.scheduler.sync()
        return state.scheduler.decorate(job)
    return job


@router.patch("/jobs/{job_id}")
def patch_job(job_id: str, body: JobPatch, state: State) -> Job:
    if body.cron is not None:
        _check_cron(body.cron)
    with state.db.session() as conn:
        job = repo.agents.patch_job(conn, job_id, body)
    if job is None:
        raise NotFound("Job")
    if state.scheduler:
        state.scheduler.sync()
        return state.scheduler.decorate(job)
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, state: State) -> dict[str, str]:
    with state.db.session() as conn:
        if not repo.agents.delete_job(conn, job_id):
            raise NotFound("Job")
    if state.scheduler:
        state.scheduler.sync()
    return {"status": "deleted"}


@router.post("/jobs/{job_id}/run")
async def run_now(job_id: str, state: State) -> JobRun:
    """Run it immediately. The same code path the scheduler uses, so what you test is what fires."""
    with state.db.session() as conn:
        job = repo.agents.get_job(conn, job_id)
    if job is None:
        raise NotFound("Job")
    run_id = await loop.start(_runtime(state), job)
    with state.db.session() as conn:
        run = repo.agents.get_run(conn, run_id)
    assert run is not None
    return run


@router.get("/runs")
def list_runs(state: State, job_id: str | None = None, limit: int = 50) -> list[JobRun]:
    with state.db.session() as conn:
        return repo.agents.list_runs(conn, job_id, limit)


@router.get("/runs/{run_id}/calls")
def run_calls(run_id: str, state: State) -> list[PendingCall]:
    """Every tool call this run made, in order, whatever became of it."""
    with state.db.session() as conn:
        return repo.tools.for_run(conn, run_id)


@router.get("/inbox")
def inbox(state: State, limit: int = 100) -> list[InboxItem]:
    with state.db.session() as conn:
        return repo.agents.list_inbox(conn, limit)


class ReadFlag(BaseModel):
    read: bool = True


@router.post("/inbox/{item_id}/read")
def mark_read(item_id: str, body: ReadFlag, state: State) -> InboxItem:
    with state.db.session() as conn:
        item = repo.agents.mark_read(conn, item_id, body.read)
    if item is None:
        raise NotFound("Inbox item")
    return item
