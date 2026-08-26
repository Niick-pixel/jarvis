"""The agent loop: generate, read the tool blocks, run what is allowed, wait for what is not.

The whole loop is a state machine over rows. Each pass looks at the run's `tool_calls` and does the
single thing they call for - wait at the gate, run a cleared call, hand results back, or generate.
Nothing lives only in the task, so a run parked overnight resumes from disk the moment you approve.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from server.agents import compose
from server.agents.approvals import Approvals
from server.chat import run as runner
from server.chat.execute import execute as generate
from server.chat.live import LiveRuns
from server.db import repo
from server.db.connection import Database
from server.models.agents import Job
from server.models.conversation import ConversationCreate
from server.models.stream import ChatRequest
from server.models.tools import PendingCall
from server.providers.registry import ProviderRegistry
from server.settings import Settings
from server.tools import dispatch, gate, sandbox
from server.tools.builtin import ToolContext

log = logging.getLogger("jarvis.agents")


@dataclass(frozen=True)
class Runtime:
    db: Database
    registry: ProviderRegistry
    settings: Settings
    live: LiveRuns
    approvals: Approvals


async def start(rt: Runtime, job: Job) -> str:
    """Create the run's conversation and drive it in the background."""
    with rt.db.session() as conn:
        conversation = repo.conversations.create(
            conn,
            ConversationCreate(
                title=compose.title_for(job), system_prompt=compose.system_prompt(job)
            ),
        )
        job_run_id = repo.agents.start_run(conn, job.id, conversation.id)
    asyncio.get_running_loop().create_task(_drive(rt, job_run_id))
    return job_run_id


async def resume(rt: Runtime, job_run_id: str) -> None:
    """Pick a parked run back up. A no-op if a driver is already on it."""
    if rt.approvals.is_driving(job_run_id):
        rt.approvals.notify(job_run_id)
        return
    asyncio.get_running_loop().create_task(_drive(rt, job_run_id))


async def _drive(rt: Runtime, job_run_id: str) -> None:
    if not rt.approvals.claim(job_run_id):
        return
    try:
        await _loop(rt, job_run_id)
    except Exception as exc:  # noqa: BLE001 - a job run must fail as a row, never as a traceback
        log.exception("job run %s failed", job_run_id)
        with rt.db.session() as conn:
            repo.agents.set_status(conn, job_run_id, "failed", error=str(exc)[:400])
    finally:
        rt.approvals.release(job_run_id)


async def _loop(rt: Runtime, job_run_id: str) -> None:
    while True:
        with rt.db.session() as conn:
            run = repo.agents.get_run(conn, job_run_id)
            if run is None or run.status in ("done", "failed", "cancelled"):
                return
            job = repo.agents.get_job(conn, run.job_id)
            if job is None:
                repo.agents.set_status(conn, job_run_id, "failed", error="the job was deleted")
                return
            calls = repo.tools.for_run(conn, job_run_id)
            steps = run.steps

        # Order matters: run what is already cleared, then park on what is not, and only hand
        # results back once the whole batch has an outcome. A batch delivered piecemeal would let
        # the model act on half of what it asked for and never learn the rest was refused.
        cleared = [c for c in calls if c.status == "approved" and not c.delivered]
        if cleared:
            await _run_call(rt, job, job_run_id, cleared[0].id)
            continue

        if any(c.status == "pending" for c in calls):
            await _wait_for_decisions(rt, job_run_id)
            continue

        undelivered = [
            c for c in calls if c.status in ("ran", "failed", "denied") and not c.delivered
        ]
        if undelivered:
            _deliver(rt, run.conversation_id or "", undelivered, steps=steps + 1, run_id=job_run_id)
            continue

        if steps >= rt.settings.agents.max_steps:
            _finish(rt, job, job_run_id, "", ["reached the step limit before reaching an answer"])
            return

        answer, notes = await _generate_step(rt, job, run.conversation_id or "")
        calls_out, malformed = gate.parse_calls(answer)
        notes += [f"malformed tool block: {m}" for m in malformed]
        if not calls_out:
            _finish(rt, job, job_run_id, answer, notes)
            return
        _enqueue(rt, job, job_run_id, calls_out)


async def _wait_for_decisions(rt: Runtime, job_run_id: str) -> bool:
    """Park at the gate. Returns False when the wait expired and the calls were denied."""
    with rt.db.session() as conn:
        repo.agents.set_status(conn, job_run_id, "waiting_approval")
    waiter = rt.approvals.waiter(job_run_id)
    timeout = rt.settings.agents.approval_timeout_minutes * 60
    try:
        await asyncio.wait_for(waiter.wait(), timeout=timeout)
    except TimeoutError:
        with rt.db.session() as conn:
            repo.tools.expire_pending(
                conn, job_run_id, f"nobody decided within {timeout // 60} minutes"
            )
        return False
    finally:
        rt.approvals.clear(job_run_id)
    with rt.db.session() as conn:
        repo.agents.set_status(conn, job_run_id, "running")
    return True


def context_for(rt: Runtime, job: Job) -> ToolContext:
    """Read where you already pointed the app; write only inside the job's own workspace."""
    with rt.db.session() as conn:
        roots = [Path(r["path"]) for r in conn.execute("SELECT path FROM sources")]
    roots.append(rt.settings.paths.memory_dir)
    workspace = job.workspace or str(rt.settings.agents.workspace / job.id)
    return ToolContext(sandbox=sandbox.build(roots, workspace), settings=rt.settings)


async def _run_call(rt: Runtime, job: Job, job_run_id: str, call_id: str) -> None:
    ctx = context_for(rt, job)
    with rt.db.session() as conn:
        planned = gate.restore(conn, call_id, ctx)
        if planned is None:
            repo.tools.set_decision(conn, call_id, False)
            return
        actor = f"job:{job.name}"
    with rt.db.session() as conn:
        await dispatch.execute(
            conn, planned, ctx, actor=actor, job_run_id=job_run_id, call_id=call_id
        )


def _deliver(
    rt: Runtime,
    conversation_id: str,
    calls: list[PendingCall],
    *,
    steps: int,
    run_id: str,
) -> None:
    """Hand every finished call back in one user turn, wrapped as data, and mark them delivered."""
    with rt.db.session() as conn:
        conversation = repo.conversations.get(conn, conversation_id)
        outputs = {c.id: c.result for c in calls}
        message = repo.messages.create(
            conn,
            conversation_id=conversation_id,
            role="user",
            content=compose.results_message(calls, outputs),
            parent_id=conversation.active_leaf_id if conversation else None,
        )
        repo.conversations.touch(conn, conversation_id, active_leaf_id=message.id)
        repo.tools.mark_delivered(conn, [c.id for c in calls])
        repo.agents.set_status(conn, run_id, "running", steps=steps)


async def _generate_step(rt: Runtime, job: Job, conversation_id: str) -> tuple[str, list[str]]:
    """One turn. The job prompt opens the conversation; later turns continue from the results."""
    with rt.db.session() as conn:
        opening = not repo.messages.list_for_conversation(conn, conversation_id)
    body = ChatRequest(conversation_id=conversation_id, content=job.prompt if opening else None)
    prepared = await runner.prepare(rt.db, rt.registry, rt.settings, body)
    rt.live.start(prepared.run_id, prepared.message_id, prepared.conversation_id)
    await generate(rt.db, rt.live, prepared)
    with rt.db.session() as conn:
        message = repo.messages.get(conn, prepared.message_id)
    if message is None:
        return "", ["the generated message vanished"]
    stopped = message.status != "complete"
    return message.content, [f"generation ended as {message.status}"] if stopped else []


def _enqueue(rt: Runtime, job: Job, job_run_id: str, calls: list[gate.ModelToolCall]) -> None:
    """Record the whole batch at once: gated calls wait for you, the rest are cleared to run."""
    ctx = context_for(rt, job)
    with rt.db.session() as conn:
        for planned in gate.plan(conn, calls, allowed=job.tools, ctx=ctx):
            if gate.already_denied(conn, planned, job_run_id):
                refused = planned_with(planned, "you already denied this call in this run")
                dispatch.record_refusal(conn, refused, job_run_id, f"job:{job.name}")
            elif planned.refusal:
                dispatch.record_refusal(conn, planned, job_run_id, f"job:{job.name}")
            elif planned.needs_approval:
                dispatch.enqueue(conn, planned, job_run_id)
            else:
                dispatch.clear(conn, planned, job_run_id)


def planned_with(planned: gate.Planned, refusal: str) -> gate.Planned:
    return gate.Planned(planned.call, planned.tool, planned.target, planned.scope, refusal=refusal)


def _finish(rt: Runtime, job: Job, job_run_id: str, answer: str, notes: list[str]) -> None:
    with rt.db.session() as conn:
        body, flags = compose.report(
            conn, job=job, job_run_id=job_run_id, answer=answer, notes=notes
        )
        repo.agents.add_inbox(
            conn, job_run_id=job_run_id, title=compose.title_for(job), body=body, flags=flags
        )
        repo.agents.set_status(conn, job_run_id, "done", summary=body.split("\n")[0][:200])
