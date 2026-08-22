"""Any OpenAI-compatible endpoint: LM Studio, Ollama's /v1, vLLM, or a hosted frontier model.

No prefix continuation here - the chat-completions shape has no way to say "keep writing this
exact assistant turn". Capabilities report that honestly and live steering degrades visibly.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from server.models.params import SamplingParams
from server.models.provider import Capabilities, ModelInfo, ProviderInfo, ProviderKind
from server.models.stream import Alternative
from server.providers.base import (
    PromptMessage,
    ProviderError,
    StreamItem,
    Token,
    Usage,
    capabilities_for,
)
from server.providers.httpsse import iter_sse_json

DEFAULT_CTX = 8192


class OpenAICompatProvider:
    kind: ProviderKind = "openai"

    def __init__(
        self,
        base_url: str,
        name: str = "openai-compatible",
        *,
        api_key: str = "",
        kind: ProviderKind | None = None,
        accepts_extra_sampling: bool = True,
        default_ctx: int = DEFAULT_CTX,
        timeout: float = 600.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_ctx = default_ctx
        self.accepts_extra_sampling = accepts_extra_sampling
        self._timeout = timeout
        if kind is not None:
            self.kind = kind

    def _client(self) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout, headers=headers)

    def capabilities(self) -> Capabilities:
        return capabilities_for(self.kind)

    async def info(self) -> ProviderInfo:
        try:
            models = await self.list_models()
        except Exception as exc:  # noqa: BLE001 - shown verbatim, never swallowed
            return ProviderInfo(
                name=self.name,
                kind=self.kind,
                base_url=self.base_url,
                online=False,
                capabilities=self.capabilities(),
                detail=f"{type(exc).__name__}: {exc}",
            )
        return ProviderInfo(
            name=self.name,
            kind=self.kind,
            base_url=self.base_url,
            online=True,
            capabilities=self.capabilities(),
            models=[m.id for m in models],
        )

    async def list_models(self) -> list[ModelInfo]:
        async with self._client() as client:
            resp = await client.get("/v1/models", timeout=10.0)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        caps = self.capabilities()
        out: list[ModelInfo] = []
        for entry in data:
            raw_id = str(entry.get("id", ""))
            if not raw_id:
                continue
            ctx = entry.get("max_context_length") or entry.get("context_length")
            out.append(
                ModelInfo(
                    id=f"{self.kind}:{raw_id}",
                    provider=self.kind,
                    display_name=raw_id,
                    ctx_len_max=int(ctx) if ctx else self.default_ctx,
                    supports_logprobs=caps.logprobs,
                    supports_prefix=caps.prefix_continuation,
                )
            )
        return out

    async def count_tokens(self, text: str, model_id: str) -> int | None:
        """No tokenizer endpoint exists in this API. The caller estimates and labels it."""
        return None

    def _body(
        self,
        messages: list[PromptMessage],
        params: SamplingParams,
        model_name: str,
        assistant_prefix: str | None,
    ) -> dict[str, Any]:
        payload = [m.model_dump() for m in messages]
        if assistant_prefix:
            payload.append({"role": "assistant", "content": assistant_prefix})
        body: dict[str, Any] = {
            "model": model_name,
            "messages": payload,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": params.temperature,
            "top_p": params.top_p,
            "max_tokens": params.max_tokens,
            "seed": params.seed,
        }
        if params.n_probs > 0 and self.capabilities().logprobs:
            body["logprobs"] = True
            body["top_logprobs"] = params.n_probs
        if self.accepts_extra_sampling:
            body["top_k"] = params.top_k
            body["repeat_penalty"] = params.repeat_penalty
        return body

    async def stream(
        self,
        messages: list[PromptMessage],
        params: SamplingParams,
        *,
        model_id: str,
        ctx_len: int,
        assistant_prefix: str | None = None,
    ) -> AsyncIterator[StreamItem]:
        model_name = model_id.split(":", 1)[-1]
        body = self._body(messages, params, model_name, assistant_prefix)
        started = time.perf_counter()
        usage = Usage()
        async with self._client() as client:
            try:
                async with client.stream("POST", "/v1/chat/completions", json=body) as resp:
                    if resp.status_code != 200:
                        detail = (await resp.aread()).decode(errors="replace")[:400]
                        raise ProviderError(f"{self.name} returned {resp.status_code}: {detail}")
                    async for chunk in iter_sse_json(resp):
                        for item in self._chunk_to_items(chunk, started, usage):
                            yield item
            except httpx.HTTPError as exc:
                raise ProviderError(f"{self.name} connection failed: {exc}") from exc
        usage.gen_ms = usage.gen_ms or int((time.perf_counter() - started) * 1000)
        yield usage

    def _chunk_to_items(
        self, chunk: dict[str, Any], started: float, usage: Usage
    ) -> list[StreamItem]:
        if raw_usage := chunk.get("usage"):
            usage.prompt_tokens = int(raw_usage.get("prompt_tokens") or usage.prompt_tokens)
            usage.gen_tokens = int(raw_usage.get("completion_tokens") or usage.gen_tokens)
        choices = chunk.get("choices") or []
        if not choices:
            return []
        choice = choices[0]
        if reason := choice.get("finish_reason"):
            usage.stop_reason = "length" if reason == "length" else "eos"
        text = (choice.get("delta") or {}).get("content") or ""
        if not text:
            return []
        logprob, alts = _logprobs_for(choice)
        return [
            Token(
                text=text,
                logprob=logprob,
                top_alternatives=alts,
                timing_ms=(time.perf_counter() - started) * 1000,
            )
        ]


def _logprobs_for(choice: dict[str, Any]) -> tuple[float | None, list[Alternative] | None]:
    content = (choice.get("logprobs") or {}).get("content") or []
    if not content:
        return None, None
    entry = content[0]
    alts = [
        Alternative(token=a.get("token", ""), logprob=float(a.get("logprob", 0.0)))
        for a in entry.get("top_logprobs", [])
    ]
    return float(entry.get("logprob", 0.0)), alts or None
