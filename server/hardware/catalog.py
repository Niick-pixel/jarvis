"""Ranking the model catalogue against this machine's budget.

Split out of recommend.py, which owns the arithmetic; this owns the judgement calls about what
counts as fitting, tight, or too big.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from server.hardware.recommend import budget_for, max_ctx_for
from server.models.hardware import FitStatus, GpuInfo, ModelRecommendation, VramBudget
from server.models.provider import ModelInfo


def load_catalog(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as handle:
        return list(tomllib.load(handle).get("model", []))


def rank_catalog(
    entries: list[dict[str, Any]],
    *,
    gpu: GpuInfo | None,
    browser_reserve_mb: int,
    kv_dtype: str = "q8_0",
    installed: set[str] | None = None,
) -> list[ModelRecommendation]:
    """Rank by what fits, largest-that-fits first. Oversized models stay visible with the reason."""
    installed = installed or set()
    out: list[ModelRecommendation] = []
    for entry in entries:
        info = ModelInfo(
            id=entry["key"],
            provider="llamacpp",
            display_name=entry["display_name"],
            ctx_len_max=int(entry["ctx_len_max"]),
            quant=entry.get("quant"),
        )
        params_b = float(entry.get("params_b", 8.0))
        ctx = max_ctx_for(
            info,
            gpu=gpu,
            browser_reserve_mb=browser_reserve_mb,
            kv_dtype=kv_dtype,
            params_b=params_b,
        )
        budget = budget_for(
            info,
            ctx_len=ctx,
            gpu=gpu,
            browser_reserve_mb=browser_reserve_mb,
            kv_dtype=kv_dtype,
            params_b=params_b,
        )
        status, note = _status_for(budget, ctx, int(entry["ctx_len_max"]), gpu)
        out.append(
            ModelRecommendation(
                key=entry["key"],
                display_name=entry["display_name"],
                why=entry.get("why", ""),
                quant=entry.get("quant", "Q4_K_M"),
                params_b=params_b,
                ctx_len_max=int(entry["ctx_len_max"]),
                recommended_ctx_len=ctx,
                status=status,
                note=note,
                tags=list(entry.get("tags", [])),
                installed=entry["key"] in installed,
            )
        )
    order: dict[FitStatus, int] = {"fits": 0, "tight": 1, "needs_offload": 2, "unavailable": 3}
    # With a GPU, the largest model that fits is the best answer. Without one, everything runs on
    # CPU and the smallest is, so the tiebreak flips rather than the message being wrong.
    size_key = (lambda r: r.params_b) if gpu is None else (lambda r: -r.params_b)
    out.sort(key=lambda r: ("embedding" in r.tags, order[r.status], size_key(r)))
    return out


def _status_for(
    budget: VramBudget, ctx: int, model_ctx_max: int, gpu: GpuInfo | None
) -> tuple[FitStatus, str]:
    if gpu is None:
        return "needs_offload", "No GPU detected - this would run on CPU."
    if not budget.fits:
        short = budget.total_required_mb - budget.vram_free_mb
        return "needs_offload", (
            f"Needs about {short} MB more than this card has free, so part of it would sit in "
            "system RAM. `make models` benches the real tokens/sec before you commit."
        )
    at_own_ceiling = ctx >= min(budget.ctx_len, model_ctx_max)
    if budget.headroom_mb < 700:
        return "tight", (
            f"Fits at {ctx // 1024}K context, but with only {budget.headroom_mb} MB to spare - "
            "close enough that a second browser window could push it over."
        )
    if ctx < 16384 and not at_own_ceiling:
        return "tight", (
            f"Fits, but this card can only hold {ctx // 1024}K of its "
            f"{model_ctx_max // 1024}K context."
        )
    if at_own_ceiling and ctx < 16384:
        return "fits", f"Fits at {ctx // 1024}K, which is this model's own ceiling."
    return "fits", f"Fits fully offloaded at {ctx // 1024}K context."
