"""Application factory. Binds loopback, migrates on start, serves the built frontend if present."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.api import (
    chat,
    context,
    conversations,
    hardware,
    hud,
    messages,
    models_api,
    xray,
)
from server.chat.live import LiveRuns
from server.db.connection import Database
from server.db.migrate import migrate
from server.deps import AppState, State
from server.errors import SovereignError, handle_sovereign_error
from server.providers.registry import ProviderRegistry
from server.settings import Settings, load_settings

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


class Health(BaseModel):
    status: str
    version: str
    migrations_applied: list[str]
    sqlite_vec: bool
    sqlite_vec_error: str = ""
    bind: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.paths.db_path)
    registry = ProviderRegistry.from_settings(settings)
    state = AppState(settings=settings, db=db, registry=registry, live=LiveRuns())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with db.session() as conn:
            app.state.migrations = migrate(conn)
        yield

    app = FastAPI(
        title="Jarvis",
        version="0.1.0",
        summary="A local-first AI workspace",
        lifespan=lifespan,
    )
    app.state.app = state
    app.state.migrations = []
    app.add_exception_handler(SovereignError, handle_sovereign_error)

    @app.get("/api/health", tags=["health"])
    def health(state: State) -> Health:
        return Health(
            status="ok",
            version="0.1.0",
            migrations_applied=list(app.state.migrations),
            sqlite_vec=state.db.vec_available,
            sqlite_vec_error=state.db.vec_error,
            bind=f"{state.settings.server.host}:{state.settings.server.port}",
        )

    for router in (
        conversations.router,
        chat.router,
        models_api.router,
        hardware.router,
        messages.router,
        context.router,
        xray.router,
        hud.router,
    ):
        app.include_router(router)

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    return app


app = create_app()
