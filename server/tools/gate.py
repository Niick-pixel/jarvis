"""The boundary. Nothing with a side effect crosses it without you, and nothing crosses it that
did not come out of the model's own mouth.

Two separate rules live here, and they are enforced by construction rather than by discipline:

1. **Provenance.** A `ModelToolCall` cannot be built by calling its constructor - it carries a
   private channel token that only `parse_calls()` holds, and `parse_calls()` takes exactly one
   argument: the text the model generated. Retrieved documents reach the model inside a data
   envelope and are never handed to this parser, so a web page that writes a tool block is a web
   page that wrote some text (BRIEF.md 7).
2. **Approval.** Every side-effectful tool is `pending` until you decide, and a decision is a row.
   "Always allow" is always scoped to a directory or a host, never to everything.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from server.ids import now_ms
from server.models.tools import ToolGrant
from server.tools import registry
from server.tools.builtin import ToolContext
from server.tools.registry import Tool

CALL_BLOCK = re.compile(r"```tool\s*\n(.*?)```", re.DOTALL)
_CHANNEL = object()


@dataclass(frozen=True)
class ModelToolCall:
    tool: str
    args: dict[str, Any]
    channel: object = field(repr=False, default=None)

    def __post_init__(self) -> None:
        if self.channel is not _CHANNEL:
            raise TypeError(
                "A tool call can only come from parse_calls() reading the model's own output. "
                "Text that arrived from a document or a web page is data, never a call."
            )


def parse_calls(assistant_output: str) -> tuple[list[ModelToolCall], list[str]]:
    """Read tool blocks out of one assistant turn. The only argument is what the model generated."""
    calls: list[ModelToolCall] = []
    problems: list[str] = []
    for block in CALL_BLOCK.findall(assistant_output):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as exc:
            problems.append(f"a tool block was not valid JSON ({exc.msg})")
            continue
        name = parsed.get("tool") if isinstance(parsed, dict) else None
        if not isinstance(name, str):
            problems.append("a tool block had no `tool` name")
            continue
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        calls.append(ModelToolCall(tool=name, args=args, channel=_CHANNEL))
    return calls, problems


@dataclass(frozen=True)
class Planned:
    call: ModelToolCall
    tool: Tool | None
    target: str
    scope: str
    refusal: str = ""
    needs_approval: bool = False


def plan(
    conn: sqlite3.Connection, calls: list[ModelToolCall], *, allowed: list[str], ctx: ToolContext
) -> list[Planned]:
    out: list[Planned] = []
    for call in calls:
        tool = registry.get(call.tool)
        if tool is None:
            out.append(Planned(call, None, "", "", refusal=f"there is no tool called {call.tool}"))
            continue
        target = tool.target(call.args)
        scope = scope_for(tool, target, ctx)
        if call.tool not in allowed:
            out.append(
                Planned(call, tool, target, scope, refusal=f"this job may not use {call.tool}")
            )
            continue
        out.append(
            Planned(
                call,
                tool,
                target,
                scope,
                needs_approval=tool.side_effect and not is_granted(conn, tool.name, scope),
            )
        )
    return out


def scope_for(tool: Tool, target: str, ctx: ToolContext) -> str:
    """What "always allow here" would mean for this call: a directory, a host, or the workspace."""
    if tool.target_kind == "path":
        try:
            resolved = Path(target).expanduser().resolve()
        except OSError:
            return ""
        return str(resolved.parent if resolved.suffix else resolved)
    if tool.target_kind == "host":
        return urlparse(target).hostname or ""
    return str(ctx.sandbox.cwd)


def is_granted(conn: sqlite3.Connection, tool: str, scope: str) -> bool:
    if not scope:
        return False
    rows = conn.execute("SELECT scope FROM tool_grants WHERE tool = ?", (tool,))
    return any(
        scope == row["scope"] or scope.startswith(row["scope"].rstrip("/") + "/") for row in rows
    )


def grant(conn: sqlite3.Connection, tool: str, scope: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tool_grants (tool, scope, created_at) VALUES (?,?,?)",
        (tool, scope, now_ms()),
    )


def revoke(conn: sqlite3.Connection, tool: str, scope: str) -> None:
    conn.execute("DELETE FROM tool_grants WHERE tool = ? AND scope = ?", (tool, scope))


def grants(conn: sqlite3.Connection) -> list[ToolGrant]:
    rows = conn.execute("SELECT * FROM tool_grants ORDER BY created_at DESC")
    return [ToolGrant(tool=r["tool"], scope=r["scope"], created_at=r["created_at"]) for r in rows]


def already_denied(conn: sqlite3.Connection, planned: Planned, job_run_id: str | None) -> bool:
    """Have you already said no to exactly this, in this run?

    Without this a job that keeps asking parks at the gate again on every step, and the gate turns
    into a nag box - which is how people learn to approve things without reading them.
    """
    if job_run_id is None:
        return False
    args = json.dumps(planned.call.args)
    row = conn.execute(
        "SELECT 1 FROM tool_calls WHERE job_run_id = ? AND tool = ? AND args_json = ?"
        " AND status = 'denied' LIMIT 1",
        (job_run_id, planned.call.tool, args),
    ).fetchone()
    return row is not None


def restore(conn: sqlite3.Connection, call_id: str, ctx: ToolContext) -> Planned | None:
    """Rebuild a planned call from its row, so an approval can run days after it was requested.

    This is the one other place a `ModelToolCall` is built, and it is not a hole in the rule: the
    row can only have been written by `enqueue()`, which only accepts a call that `parse_calls()`
    produced. Provenance survives the round trip through disk rather than being re-established.
    """
    row = conn.execute("SELECT * FROM tool_calls WHERE id = ?", (call_id,)).fetchone()
    if row is None:
        return None
    tool = registry.get(row["tool"])
    if tool is None:
        return None
    call = ModelToolCall(tool=row["tool"], args=json.loads(row["args_json"]), channel=_CHANNEL)
    return Planned(call, tool, row["target"], scope_for(tool, row["target"], ctx))
