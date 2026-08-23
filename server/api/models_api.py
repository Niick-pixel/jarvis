from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from server.db import repo
from server.deps import State
from server.hardware import probe, selection
from server.models.hardware import ModelOption
from server.models.provider import ModelInfo, ProviderInfo

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/providers")
async def list_providers(state: State) -> list[ProviderInfo]:
    return await state.registry.infos()


@router.get("/models")
async def list_models(state: State) -> list[ModelInfo]:
    return await state.registry.models()


@router.get("/models/options")
async def model_options(state: State) -> list[ModelOption]:
    """Every reachable model, judged against this machine, best first.

    This is the same ranking the app uses to pick a model on its own, so what the picker shows and
    what the app does cannot disagree.
    """
    gpus, _ = probe.probe_gpus()
    return selection.rank(
        await state.registry.models(),
        gpu=gpus[0] if gpus else None,
        browser_reserve_mb=state.settings.hardware.browser_vram_reserve_mb,
        kv_dtype=state.settings.hardware.kv_cache_dtype,
    )


class SelectedModel(BaseModel):
    model_id: str | None = None
    """None means "decide automatically from the hardware on every request"."""


@router.get("/models/selected")
def get_selected(state: State) -> SelectedModel:
    with state.db.session() as conn:
        return SelectedModel(model_id=repo.settings.get(conn, repo.settings.SELECTED_MODEL))


@router.put("/models/selected")
def set_selected(body: SelectedModel, state: State) -> SelectedModel:
    with state.db.session() as conn:
        if body.model_id:
            repo.settings.put(conn, repo.settings.SELECTED_MODEL, body.model_id)
        else:
            repo.settings.clear(conn, repo.settings.SELECTED_MODEL)
    return body
