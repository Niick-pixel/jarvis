"""Shared application state, reached through one typed accessor instead of loose globals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from server.chat.live import LiveRuns
from server.db.connection import Database
from server.providers.registry import ProviderRegistry
from server.settings import Settings


@dataclass
class AppState:
    settings: Settings
    db: Database
    registry: ProviderRegistry
    live: LiveRuns


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.app
    return state


State = Annotated[AppState, Depends(get_state)]
"""Inject as `state: State`. The Annotated form keeps FastAPI happy and linters quiet."""
