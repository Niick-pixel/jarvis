"""What a backend can actually do. Features are hidden when unsupported, never faked."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ProviderKind = Literal["llamacpp", "ollama", "lmstudio", "openai", "vllm", "fake"]


class Capabilities(BaseModel):
    logprobs: bool = False
    """Per-token logprobs + alternatives. False hides the x-ray UI for this model (BRIEF.md 4.3)."""
    prefix_continuation: bool = False
    """A raw completion endpoint, so a nudge can resume from the partial text and reuse the KV
    cache. False means live steering falls back to re-sending the partial, and says so."""
    embeddings: bool = False
    tokenize: bool = False
    """An exact tokenizer. False makes context accounting estimated, and the UI labels it."""


class ProviderInfo(BaseModel):
    name: str
    kind: ProviderKind
    base_url: str
    online: bool
    capabilities: Capabilities
    models: list[str] = []
    detail: str = ""
    """Human-readable reason when offline, shown verbatim in the UI."""


class ModelInfo(BaseModel):
    id: str
    provider: ProviderKind
    display_name: str
    ctx_len_max: int
    quant: str | None = None
    size_bytes: int | None = None
    file_path: str | None = None
    sha256: str | None = None
    n_layers: int | None = None
    n_kv_heads: int | None = None
    head_dim: int | None = None
    """The three GGUF fields the KV-cache formula needs (PLAN.md 1.1)."""
    supports_logprobs: bool = False
    supports_prefix: bool = False
    bench_gen_tps: float | None = None
    bench_prompt_tps: float | None = None
    """Measured on this machine by `make models`, never copied from a table."""
