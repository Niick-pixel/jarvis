"""Ambient agents: scheduled jobs, their runs, and the inbox they report into (BRIEF.md 4.9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

JobRunStatus = Literal["running", "waiting_approval", "done", "failed", "cancelled"]


class JobCreate(BaseModel):
    name: str
    cron: str
    """Standard five-field cron, in local time. Validated before the job is stored."""
    prompt: str
    tools: list[str] = []
    """The tools this run may ask for. A job cannot widen its own set while running."""
    workspace: str = ""
    """The single directory its file writes may touch. Empty means it cannot write at all."""
    enabled: bool = True


class JobPatch(BaseModel):
    name: str | None = None
    cron: str | None = None
    prompt: str | None = None
    tools: list[str] | None = None
    workspace: str | None = None
    enabled: bool | None = None


class Job(BaseModel):
    id: str
    name: str
    cron: str
    prompt: str
    tools: list[str] = []
    workspace: str = ""
    enabled: bool
    created_at: int
    last_run_at: int | None = None
    next_run_at: int | None = None
    """From the live scheduler, not from the row: a disabled or unparsed job simply has none."""


class JobRun(BaseModel):
    id: str
    job_id: str
    job_name: str = ""
    conversation_id: str | None = None
    """The run's transcript is an ordinary conversation, readable with every existing tool."""
    status: JobRunStatus
    started_at: int
    finished_at: int | None = None
    steps: int = 0
    summary: str = ""
    error: str = ""


class InboxItem(BaseModel):
    id: str
    created_at: int
    job_run_id: str | None = None
    title: str
    body: str
    flags: list[str] = []
    """Why this wants your eyes. `injection` means a document tried to give instructions."""
    read_at: int | None = None
