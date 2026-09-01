"""Shared application state, reached through one typed accessor instead of loose globals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from server.agents.approvals import Approvals
from server.chat.live import LiveRuns
from server.db.connection import Database
from server.knowledge.indexer import Indexer
from server.knowledge.watcher import Watcher
from server.models.memory import MemoryBatch
from server.providers.launcher import LlamaServer
from server.providers.registry import ProviderRegistry
from server.settings import Settings

if TYPE_CHECKING:  # the scheduler imports the loop, which imports this module
    from server.agents.scheduler import JobScheduler


@dataclass
class AppState:
    settings: Settings
    db: Database
    registry: ProviderRegistry
    live: LiveRuns
    indexer: Indexer
    watcher: Watcher
    approvals: Approvals = field(default_factory=Approvals)
    """Who is waiting at the tool gate. Held here so a decision in the UI reaches the parked run."""
    scheduler: JobScheduler | None = None
    """None only before the lifespan starts, and in tests that never fire a job."""
    llama: LlamaServer | None = None
    """The llama-server this process started, if it started one. None when autostart is off."""
    extractions: dict[str, asyncio.Task[MemoryBatch]] = field(default_factory=dict)
    """In-flight memory extractions, keyed by the message that triggered them, so the client can
    await the one it caused instead of polling for it."""


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.app
    return state


State = Annotated[AppState, Depends(get_state)]
"""Inject as `state: State`. The Annotated form keeps FastAPI happy and linters quiet."""
