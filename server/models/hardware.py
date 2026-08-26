"""Hardware facts and the VRAM arithmetic. On an 8-12GB card this is the whole design constraint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from server.errors import Remedy
from server.models.provider import ModelInfo


class GpuInfo(BaseModel):
    index: int
    name: str
    vram_total_mb: int
    vram_free_mb: int
    vram_used_mb: int
    utilization_pct: int | None = None
    temperature_c: int | None = None
    power_w: float | None = None
    unavailable_fields: list[str] = []
    """WSL2's NVML shim often withholds power and temperature. We report `-`, never a guess."""


class HostInfo(BaseModel):
    platform: str
    is_wsl: bool
    ram_total_mb: int
    ram_available_mb: int
    """Under WSL2 this reflects the VM's ceiling (~50% of host RAM by default), not the host's."""
    cpu_count: int
    disk_free_mb: int


class HardwareReport(BaseModel):
    gpus: list[GpuInfo]
    host: HostInfo
    nvml_available: bool
    notes: list[str] = []
    """Environment-specific caveats surfaced in the UI, e.g. the /mnt/c polling warning."""


class VramBudget(BaseModel):
    """Every consumer of the card, itemised. This is what the preflight check decides on."""

    model_id: str
    ctx_len: int
    kv_dtype: Literal["f16", "q8_0"]
    weights_mb: int
    kv_cache_mb: int
    compute_buffer_mb: int
    browser_reserve_mb: int
    total_required_mb: int
    vram_total_mb: int
    vram_free_mb: int
    fits: bool
    headroom_mb: int
    explanation: str
    remedy: Remedy | None = None


FitStatus = Literal["fits", "tight", "needs_offload", "unavailable"]


class ModelOption(BaseModel):
    """A model the app can actually reach, judged against this machine."""

    model: ModelInfo
    status: FitStatus
    recommended_ctx_len: int
    reason: str
    """Plain sentence naming the limitation, shown verbatim in the picker."""
    budget: VramBudget | None = None
    remote: bool = False
    recommended: bool = False


class ModelRecommendation(BaseModel):
    key: str
    display_name: str
    why: str
    quant: str
    params_b: float
    ctx_len_max: int
    recommended_ctx_len: int
    """The largest context this card can actually hold for this model - the honest number."""
    status: FitStatus
    download_size_bytes: int | None = None
    resolved_file: str | None = None
    note: str = ""
    tags: list[str] = []
    installed: bool = False
