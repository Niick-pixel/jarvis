"""Discovery and capability negotiation across every configured backend.

Autodetect means "ask the default ports whether anything is listening", never "assume". A backend
that is down is reported as down, with the reason it gave.
"""

from __future__ import annotations

import asyncio
import time

from server.errors import SovereignError
from server.models.provider import Capabilities, ModelInfo, ProviderInfo
from server.providers.base import ModelProvider
from server.providers.llamacpp import LlamaCppProvider
from server.providers.lmstudio import LMStudioProvider
from server.providers.ollama import OllamaProvider
from server.providers.openai_compat import OpenAICompatProvider
from server.settings import Settings, is_loopback

CACHE_TTL_S = 15.0


class ProviderRegistry:
    def __init__(self, providers: list[ModelProvider]) -> None:
        self._providers = providers
        self._models: list[ModelInfo] = []
        self._infos: list[ProviderInfo] = []
        self._fetched_at = 0.0

    @classmethod
    def from_settings(cls, settings: Settings) -> ProviderRegistry:
        cfg = settings.providers
        built: list[ModelProvider] = []
        if cfg.llamacpp.enabled:
            _require_loopback(cfg.llamacpp.base_url, "llamacpp")
            built.append(LlamaCppProvider(cfg.llamacpp.base_url))
        if cfg.ollama.enabled:
            _require_loopback(cfg.ollama.base_url, "ollama")
            built.append(OllamaProvider(cfg.ollama.base_url))
        if cfg.lmstudio.enabled:
            _require_loopback(cfg.lmstudio.base_url, "lmstudio")
            built.append(LMStudioProvider(cfg.lmstudio.base_url))
        if cfg.openai.enabled and settings.openai_api_key:
            built.append(
                OpenAICompatProvider(
                    cfg.openai.base_url,
                    name="openai",
                    api_key=settings.openai_api_key,
                    kind="openai",
                    accepts_extra_sampling=False,
                )
            )
        return cls(built)

    def add(self, provider: ModelProvider) -> None:
        self._providers.append(provider)
        self._fetched_at = 0.0

    @property
    def providers(self) -> list[ModelProvider]:
        return list(self._providers)

    async def refresh(self) -> None:
        results = await asyncio.gather(*(p.info() for p in self._providers), return_exceptions=True)
        infos: list[ProviderInfo] = []
        online: list[ModelProvider] = []
        for provider, result in zip(self._providers, results, strict=True):
            if isinstance(result, BaseException):
                infos.append(
                    ProviderInfo(
                        name=provider.name,
                        kind=provider.kind,
                        base_url=provider.base_url,
                        online=False,
                        capabilities=_empty_caps(),
                        detail=f"{type(result).__name__}: {result}",
                    )
                )
                continue
            infos.append(result)
            if result.online:
                online.append(provider)
        model_lists = await asyncio.gather(
            *(p.list_models() for p in online), return_exceptions=True
        )
        models: list[ModelInfo] = []
        for listed in model_lists:
            if not isinstance(listed, BaseException):
                models.extend(listed)
        self._infos, self._models, self._fetched_at = infos, models, time.monotonic()

    async def _ensure_fresh(self) -> None:
        if time.monotonic() - self._fetched_at > CACHE_TTL_S:
            await self.refresh()

    async def infos(self) -> list[ProviderInfo]:
        await self._ensure_fresh()
        return self._infos

    async def models(self) -> list[ModelInfo]:
        await self._ensure_fresh()
        return self._models

    async def resolve(self, model_id: str | None) -> tuple[ModelProvider, ModelInfo]:
        models = await self.models()
        if not models:
            raise SovereignError(
                "provider_unavailable",
                "No model is reachable. Start llama.cpp (`make dev` can do it), open LM Studio "
                "or Ollama, or configure an OpenAI-compatible endpoint.",
                status_code=503,
            )
        chosen = next((m for m in models if m.id == model_id), None) if model_id else models[0]
        if chosen is None:
            raise SovereignError(
                "not_found", f"Model {model_id!r} is not available", status_code=404
            )
        for provider in self._providers:
            if provider.kind == chosen.provider:
                return provider, chosen
        raise SovereignError(
            "provider_unavailable", f"No provider for {chosen.id}", status_code=503
        )


def _require_loopback(url: str, name: str) -> None:
    """A local inference port must not be reachable off-box (BRIEF.md 7)."""
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if not is_loopback(host):
        raise SovereignError(
            "invalid_request",
            f"Refusing to register {name}: {url} is not loopback. Local inference ports must "
            "never be exposed off-box.",
        )


def _empty_caps() -> Capabilities:
    return Capabilities()
