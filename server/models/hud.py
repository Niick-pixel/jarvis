"""The Sovereign HUD (BRIEF.md 4.10). A vanity metric, and satisfying, which is the point."""

from __future__ import annotations

from pydantic import BaseModel

from server.models.hardware import GpuInfo


class HudSample(BaseModel):
    gpu: GpuInfo | None = None
    """None on a machine with no NVIDIA GPU. Fields NVML withholds stay None - never invented."""
    ram_used_mb: int
    ram_total_mb: int
    tokens_per_second: float = 0.0
    active_runs: int = 0


class LifetimeCounters(BaseModel):
    tokens_generated: float
    runs_completed: float
    cost_avoided_usd: float
    rate_per_million_usd: float
    """The assumed API price this comparison uses. Editable, and shown so it is not a magic number."""
