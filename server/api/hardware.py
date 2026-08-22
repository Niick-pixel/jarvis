from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from server.deps import State
from server.errors import NotFound
from server.hardware import probe, recommend
from server.models.hardware import HardwareReport, ModelRecommendation, VramBudget

router = APIRouter(prefix="/api/hardware", tags=["hardware"])
CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "models.toml"


@router.get("")
def hardware(state: State) -> HardwareReport:
    return probe.report(state.settings.paths.models_dir)


@router.get("/budget")
async def budget(state: State, model_id: str, ctx_len: int) -> VramBudget:
    """The itemised VRAM table for one model at one context length. Shown in the UI, not hidden."""
    models = await state.registry.models()
    model = next((m for m in models if m.id == model_id), None)
    if model is None:
        raise NotFound("Model")
    gpus, _ = probe.probe_gpus()
    return recommend.budget_for(
        model,
        ctx_len=ctx_len,
        gpu=gpus[0] if gpus else None,
        browser_reserve_mb=state.settings.hardware.browser_vram_reserve_mb,
        kv_dtype=state.settings.hardware.kv_cache_dtype,
    )


@router.get("/catalog")
def catalog(state: State) -> list[ModelRecommendation]:
    """The same ranking `make models` prints, so the UI and the CLI cannot disagree."""
    gpus, _ = probe.probe_gpus()
    return recommend.rank_catalog(
        recommend.load_catalog(CATALOG_PATH),
        gpu=gpus[0] if gpus else None,
        browser_reserve_mb=state.settings.hardware.browser_vram_reserve_mb,
        kv_dtype=state.settings.hardware.kv_cache_dtype,
    )
