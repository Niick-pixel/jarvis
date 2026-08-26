"""The gate, from outside: what tools exist, what is waiting on you, and what already happened."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter

from server.agents import loop
from server.db import repo
from server.deps import State
from server.errors import NotFound
from server.models.tools import AuditEntry, Decision, PendingCall, ToolGrant, ToolInfo
from server.tools import audit, gate, registry

router = APIRouter(prefix="/api/tools", tags=["tools"])
audit_router = APIRouter(prefix="/api/audit", tags=["tools"])


@router.get("")
def catalogue() -> list[ToolInfo]:
    """The same declarations the model is shown, so the UI and the prompt cannot disagree."""
    return registry.catalogue()


@router.get("/calls")
def calls(state: State, only_pending: bool = False, limit: int = 50) -> list[PendingCall]:
    with state.db.session() as conn:
        return repo.tools.pending(conn) if only_pending else repo.tools.recent(conn, limit)


@router.post("/calls/{call_id}")
async def decide(call_id: str, body: Decision, state: State) -> PendingCall:
    """Approve or deny one call, and optionally allow this tool here from now on."""
    with state.db.session() as conn:
        call = repo.tools.get(conn, call_id)
        if call is None:
            raise NotFound("Tool call")
        if call.status != "pending":
            return call
        repo.tools.set_decision(conn, call_id, body.approve)
        if body.approve and body.grant:
            _grant_here(conn, _runtime(state), call)
        decided = repo.tools.get(conn, call_id)
    if call.job_run_id:
        # Wake the parked run, or start a driver for it if the process restarted while it waited.
        await loop.resume(_runtime(state), call.job_run_id)
        state.approvals.notify(call.job_run_id)
    assert decided is not None
    return decided


def _runtime(state: State) -> loop.Runtime:
    return loop.Runtime(state.db, state.registry, state.settings, state.live, state.approvals)


def _grant_here(conn: sqlite3.Connection, runtime: loop.Runtime, call: PendingCall) -> None:
    """ "Always allow" means always allow *here*: the directory, or the host, this call touched."""
    tool = registry.get(call.tool)
    run = repo.agents.get_run(conn, call.job_run_id or "")
    job = repo.agents.get_job(conn, run.job_id) if run else None
    if tool is None or job is None:
        return
    scope = gate.scope_for(tool, call.target, loop.context_for(runtime, job))
    if scope:
        gate.grant(conn, call.tool, scope)


@router.get("/grants")
def grants(state: State) -> list[ToolGrant]:
    with state.db.session() as conn:
        return gate.grants(conn)


@router.delete("/grants")
def revoke(tool: str, scope: str, state: State) -> dict[str, str]:
    with state.db.session() as conn:
        gate.revoke(conn, tool, scope)
    return {"status": "revoked"}


@audit_router.get("")
def audit_log(state: State, limit: int = 200) -> list[AuditEntry]:
    """Hashes, paths and outcomes. Never arguments, never contents (BRIEF.md 7)."""
    with state.db.session() as conn:
        return audit.recent(conn, limit)
