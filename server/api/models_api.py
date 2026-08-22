from __future__ import annotations

from fastapi import APIRouter

from server.deps import State
from server.models.provider import ModelInfo, ProviderInfo

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/providers")
async def list_providers(state: State) -> list[ProviderInfo]:
    return await state.registry.infos()


@router.get("/models")
async def list_models(state: State) -> list[ModelInfo]:
    return await state.registry.models()
