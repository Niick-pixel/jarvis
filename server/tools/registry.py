"""The tool catalogue: what exists, what it touches, and which side of the gate it falls on.

A tool is declared here once. The same declaration produces the approval card, the audit target,
the list in the UI, and the protocol text the model is shown - so those four can never drift apart.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from server.models.tools import TargetKind, ToolInfo
from server.tools import builtin
from server.tools.builtin import ToolContext, ToolResult

Runner = Callable[[ToolContext, dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True)
class Tool:
    name: str
    summary: str
    side_effect: bool
    """Side effects pass the approval gate. Reads are confined by the sandbox instead."""
    target_kind: TargetKind
    args: tuple[str, ...]
    example: str
    run: Runner
    target: Callable[[dict[str, Any]], str]
    """What this call would touch, worked out before it runs, for the approval card and the log."""


def _path(args: dict[str, Any]) -> str:
    return str(args.get("path", ""))


TOOLS: dict[str, Tool] = {
    "list_dir": Tool(
        name="list_dir",
        summary="List the entries of a directory inside the allowed roots.",
        side_effect=False,
        target_kind="path",
        args=("path",),
        example='{"tool": "list_dir", "args": {"path": "~/projects"}}',
        run=builtin.list_dir,
        target=_path,
    ),
    "read_file": Tool(
        name="read_file",
        summary="Read a text file inside the allowed roots.",
        side_effect=False,
        target_kind="path",
        args=("path",),
        example='{"tool": "read_file", "args": {"path": "~/projects/README.md"}}',
        run=builtin.read_file,
        target=_path,
    ),
    "write_file": Tool(
        name="write_file",
        summary="Write a text file inside this job's workspace. Overwrites.",
        side_effect=True,
        target_kind="path",
        args=("path", "content"),
        example='{"tool": "write_file", "args": {"path": "notes/summary.md", "content": "..."}}',
        run=builtin.write_file,
        target=_path,
    ),
    "run_shell": Tool(
        name="run_shell",
        summary="Run one shell command in the workspace and return its output.",
        side_effect=True,
        target_kind="command",
        args=("command",),
        example='{"tool": "run_shell", "args": {"command": "git log --oneline -20"}}',
        run=builtin.run_shell,
        target=lambda args: str(args.get("command", "")),
    ),
    "http_get": Tool(
        name="http_get",
        summary="Fetch one public URL. Contacts that site directly, from this machine.",
        side_effect=True,
        target_kind="host",
        args=("url",),
        example='{"tool": "http_get", "args": {"url": "https://example.com/feed"}}',
        run=builtin.http_get,
        target=lambda args: str(args.get("url", "")),
    ),
}


def get(name: str) -> Tool | None:
    return TOOLS.get(name)


def catalogue() -> list[ToolInfo]:
    return [
        ToolInfo(
            name=tool.name,
            summary=tool.summary,
            side_effect=tool.side_effect,
            target_kind=tool.target_kind,
            args=list(tool.args),
            example=tool.example,
        )
        for tool in TOOLS.values()
    ]


def protocol(names: list[str]) -> str:
    """The instructions the model is given. Kept in the trusted channel, never in a document."""
    allowed = [TOOLS[n] for n in names if n in TOOLS]
    if not allowed:
        return "You have no tools in this run. Answer from what you are given."
    lines = [
        "You can use tools. To call one, emit a fenced block exactly like this, and nothing else "
        "in that block:",
        "",
        "```tool",
        '{"tool": "read_file", "args": {"path": "..."}}',
        "```",
        "",
        "One call per block; you may emit several blocks. After the calls, stop and wait: their "
        "results come back in the next turn. When you have what you need, answer normally with no "
        "tool block, and that answer is what gets delivered.",
        "",
        "Available tools:",
    ]
    for tool in allowed:
        gate = "asks for approval" if tool.side_effect else "runs immediately"
        lines.append(f"- {tool.name}({', '.join(tool.args)}) - {tool.summary} [{gate}]")
        lines.append(f"  example: {tool.example}")
    return "\n".join(lines)
