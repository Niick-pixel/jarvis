"""Private web search, and the research loop that drives it."""

from __future__ import annotations

from fastapi import APIRouter

from server.deps import State
from server.errors import SovereignError
from server.knowledge import research as research_mod
from server.knowledge import websearch
from server.models.search import ResearchReport, SearchResult, SearchStatus
from server.settings import Settings

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/status")
async def status(state: State) -> SearchStatus:
    """Whether search is actually working, and if not, why - never a silent empty result set."""
    ok, detail = await websearch.reachable(state.settings)
    return SearchStatus(
        configured=websearch.configured(state.settings),
        reachable=ok,
        base_url=state.settings.search.base_url,
        detail=detail,
    )


@router.get("")
async def search(q: str, state: State) -> list[SearchResult]:
    try:
        return await websearch.search(state.settings, q)
    except websearch.SearchUnavailable as exc:
        raise SovereignError("provider_unavailable", str(exc), status_code=503) from exc


@router.post("/research")
async def research(q: str, state: State) -> ResearchReport:
    """Plan queries, search, chase what is missing, and report the whole trail."""
    provider, model = await state.registry.resolve(None)
    return await research_mod.research(
        state.settings,
        provider,
        model_id=model.id,
        ctx_len=_ctx_len(model.ctx_len_max, state.settings),
        question=q,
    )


def _ctx_len(model_ctx: int, settings: Settings) -> int:
    return min(model_ctx or 4096, 8192)
