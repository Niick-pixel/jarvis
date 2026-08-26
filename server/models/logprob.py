"""Per-token uncertainty, as stored during generation (BRIEF.md 4.3)."""

from __future__ import annotations

from pydantic import BaseModel

from server.models.stream import Alternative


class TokenView(BaseModel):
    idx: int
    text: str
    logprob: float | None = None
    top: list[Alternative] = []
    byte_start: int
    byte_end: int
    timing_ms: float = 0.0


class NudgeMark(BaseModel):
    token_idx: int
    text: str
    created_at: int


class MessageTokens(BaseModel):
    message_id: str
    supports_logprobs: bool
    """False means this backend never reported them; the UI hides the x-ray rather than faking."""
    tokens: list[TokenView] = []
    nudges: list[NudgeMark] = []
    mean_logprob: float | None = None
    """A confidence figure, not an accuracy one - low perplexity is not truth."""
