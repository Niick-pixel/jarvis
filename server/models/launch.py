"""What `make dev` did about llama.cpp, and why (PLAN.md 8.3)."""

from __future__ import annotations

from pydantic import BaseModel


class LaunchStatus(BaseModel):
    autostart: bool
    started: bool
    """True only when this process spawned the server. A backend you started yourself is left
    alone, and says so rather than being restarted underneath you."""
    pid: int | None = None
    model_path: str = ""
    ctx_len: int = 0
    command: list[str] = []
    """The exact argv, so you can run it yourself when something about it is wrong."""
    log_path: str = ""
    detail: str = ""
    """Plain sentence: what happened, or the reason nothing did."""
