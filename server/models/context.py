"""The explicit context assembly returned with every stream (BRIEF.md 4.2).

M1 assembles system prompt + conversation history with real token counts. M2 adds interactive
pinning, toggling and reordering on top of these same shapes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

BlockKind = Literal[
    "system", "memory", "rag", "web", "pinned", "history", "tool", "nudge", "prefix"
]
EvictionReason = Literal["budget", "summarized", "user_disabled"]


class ContextBlock(BaseModel):
    id: str
    ord: int
    kind: BlockKind
    label: str
    content: str
    token_count: int
    pinned: bool = False
    included: bool = True
    eviction: EvictionReason | None = None
    source_ref: str | None = None
    """file:offset, memory entry id, or the message id this block came from."""


class EvictionNotice(BaseModel):
    """Nothing falls out of context quietly. This is rendered loudly in the UI."""

    block_id: str
    label: str
    kind: BlockKind
    token_count: int
    reason: EvictionReason


class ContextAssembly(BaseModel):
    model_id: str
    ctx_len: int
    max_gen_tokens: int
    blocks: list[ContextBlock]
    total_tokens: int
    """Sum over included blocks, counted with the model's own tokenizer where available."""
    estimated: bool = False
    """True when the provider exposes no tokenizer and counts are approximate. The UI says so."""
    evictions: list[EvictionNotice] = []
