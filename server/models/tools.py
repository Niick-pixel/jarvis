"""The tool layer as the API sees it: what exists, what is waiting on you, what already happened."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ToolCallStatus = Literal["pending", "approved", "denied", "ran", "failed"]
TargetKind = Literal["path", "host", "command", "none"]


class ToolInfo(BaseModel):
    name: str
    summary: str
    side_effect: bool
    """True means it changes something outside this process, and therefore passes the gate."""
    target_kind: TargetKind
    args: list[str]
    example: str
    """The exact call shape, which is also what the model is shown."""


class PendingCall(BaseModel):
    id: str
    job_run_id: str | None = None
    job_name: str = ""
    tool: str
    target: str
    """The path, host or command line. Shown verbatim - it is the thing you are approving."""
    args_preview: str
    """Arguments with long values elided. Never the file content being written, only its size."""
    status: ToolCallStatus
    delivered: bool = False
    """Whether the outcome has gone back to the agent yet. This is what makes a parked run
    resumable after a restart: the rows say exactly what is still outstanding."""
    created_at: int
    decided_at: int | None = None
    result: str = ""
    error: str = ""


class Decision(BaseModel):
    approve: bool
    grant: bool = False
    """Also allow this tool here from now on. Always scoped to a directory, never global."""


class ToolGrant(BaseModel):
    tool: str
    scope: str
    created_at: int


class AuditEntry(BaseModel):
    id: str
    at: int
    actor: str
    """`job:<name>` or `user`. Who caused the call, not which model produced the text."""
    tool: str
    outcome: str
    target: str = ""
    args_hash: str = ""
    result_hash: str = ""
    bytes: int = 0
    note: str = ""
