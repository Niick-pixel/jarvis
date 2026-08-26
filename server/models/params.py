"""Sampling parameters. Stored on every assistant message so a rerun is byte-reproducible."""

from __future__ import annotations

import secrets

from pydantic import BaseModel, Field


class SamplingParams(BaseModel):
    """A concrete seed is required for BRIEF.md 4.5; -1 means "pick one now and record it"."""

    seed: int = -1
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    max_tokens: int = Field(default=2048, ge=1)
    n_probs: int = Field(default=5, ge=0, le=10)
    """How many alternatives to request per token. 0 disables the x-ray for this run."""

    def resolved(self) -> SamplingParams:
        """Replace a -1 seed with a real one so the run row records what actually happened."""
        if self.seed >= 0:
            return self
        return self.model_copy(update={"seed": secrets.randbelow(2**31)})
