"""The one interface every backend is reached through. Nothing else talks to a model.

`stream()` yields `Token`s as they arrive and exactly one `Usage` as its final item. That union is
a small deviation from the brief's `AsyncIterator[Token]`, taken because the alternative - a
mutable `.last_usage` attribute read after the loop - hides timing data in provider state where a
reader cannot see it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from server.models.params import SamplingParams
from server.models.provider import Capabilities, ModelInfo, ProviderInfo, ProviderKind
from server.models.stream import Alternative


class PromptMessage(BaseModel):
    role: str
    content: str


class Token(BaseModel):
    text: str
    logprob: float | None = None
    top_alternatives: list[Alternative] | None = None
    timing_ms: float = 0.0


class Usage(BaseModel):
    prompt_tokens: int = 0
    gen_tokens: int = 0
    prompt_eval_ms: int = 0
    gen_ms: int = 0
    stop_reason: str = "eos"


StreamItem = Token | Usage


class ProviderError(RuntimeError):
    """A backend failed in a way the user needs to see, with the backend's own words."""


@runtime_checkable
class ModelProvider(Protocol):
    name: str
    kind: ProviderKind
    base_url: str

    async def info(self) -> ProviderInfo:
        """Health + negotiated capabilities. Never raises: an offline provider reports why."""
        ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def count_tokens(self, text: str, model_id: str) -> int | None:
        """Exact count from the backend's own tokenizer, or None if it has no tokenizer."""
        ...

    def stream(
        self,
        messages: list[PromptMessage],
        params: SamplingParams,
        *,
        model_id: str,
        ctx_len: int,
        assistant_prefix: str | None = None,
    ) -> AsyncIterator[StreamItem]:
        """Generate. `assistant_prefix` continues a partial assistant turn (live steering)."""
        ...


def capabilities_for(kind: ProviderKind) -> Capabilities:
    """Static baseline, refined by a live probe in each adapter's `info()`."""
    table: dict[ProviderKind, Capabilities] = {
        "llamacpp": Capabilities(
            logprobs=True, prefix_continuation=True, embeddings=True, tokenize=True
        ),
        "lmstudio": Capabilities(logprobs=True, embeddings=True),
        "openai": Capabilities(logprobs=True, embeddings=True),
        "ollama": Capabilities(embeddings=True),
        "vllm": Capabilities(logprobs=True),
        "fake": Capabilities(logprobs=True, prefix_continuation=True, tokenize=True),
    }
    return table.get(kind, Capabilities())


def estimate_tokens(text: str) -> int:
    """Fallback only, for backends with no tokenizer. Anything counted this way is flagged
    `estimated=True` all the way to the UI so no number silently pretends to be exact."""
    return max(1, round(len(text) / 3.6))
