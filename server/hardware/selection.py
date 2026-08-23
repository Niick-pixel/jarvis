"""Choosing a model for this machine, and saying plainly why the others were not chosen.

Two rules shape the ranking:

* Local before remote. The point of the project is that nothing leaves the machine, so an
  OpenAI-compatible endpoint is never auto-selected however capable it is - borrowing a frontier
  model is a deliberate act, not a default.
* Never recommend something that will not fit. A model that needs CPU offload stays visible with
  the arithmetic that rules it out, because "why can't I run this" is a fair question.
"""

from __future__ import annotations

import re
from pathlib import Path

from server.hardware.recommend import budget_for, max_ctx_for
from server.models.hardware import FitStatus, GpuInfo, ModelOption, VramBudget
from server.models.provider import ModelInfo

REMOTE_KINDS = {"openai"}
PARAMS_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)
STATUS_ORDER: dict[FitStatus, int] = {"fits": 0, "tight": 1, "unavailable": 2, "needs_offload": 3}


def infer_params_b(model: ModelInfo) -> float | None:
    """Read the parameter count out of the model's name, e.g. `qwen3-8b-q4_k_m` -> 8.0.

    Inferred, not authoritative: anything derived this way is labelled in the reason string so a
    wrong guess is visible rather than silently driving the arithmetic.
    """
    match = PARAMS_IN_NAME.search(model.display_name)
    return float(match.group(1)) if match else None


def file_size(model: ModelInfo) -> int | None:
    if model.size_bytes:
        return model.size_bytes
    if model.file_path:
        try:
            return Path(model.file_path).stat().st_size
        except OSError:
            return None
    return None


def option_for(
    model: ModelInfo,
    *,
    gpu: GpuInfo | None,
    browser_reserve_mb: int,
    kv_dtype: str,
) -> ModelOption:
    if model.provider in REMOTE_KINDS:
        return ModelOption(
            model=model,
            status="fits",
            recommended_ctx_len=model.ctx_len_max,
            remote=True,
            reason=(
                "Runs on the provider's hardware, so it costs no VRAM here - but your prompts "
                "leave this machine. Never selected automatically."
            ),
        )

    params_b = infer_params_b(model)
    sized = model.model_copy(update={"size_bytes": file_size(model)})

    if gpu is None:
        return ModelOption(
            model=sized,
            status="needs_offload",
            recommended_ctx_len=min(4096, model.ctx_len_max),
            reason="No GPU detected, so this runs on CPU. It will work, but slowly.",
        )
    if params_b is None and sized.size_bytes is None:
        return ModelOption(
            model=sized,
            status="unavailable",
            recommended_ctx_len=model.ctx_len_max,
            reason=(
                "Cannot size this model from what the backend reports, so its VRAM cost is "
                "unknown. It is still selectable; the backend will decide."
            ),
        )

    ctx = max_ctx_for(
        sized,
        gpu=gpu,
        browser_reserve_mb=browser_reserve_mb,
        kv_dtype=kv_dtype,
        params_b=params_b,
    )
    budget = budget_for(
        sized,
        ctx_len=ctx,
        gpu=gpu,
        browser_reserve_mb=browser_reserve_mb,
        kv_dtype=kv_dtype,
        params_b=params_b,
    )
    status, reason = _verdict(budget, ctx, sized)
    return ModelOption(
        model=sized,
        status=status,
        recommended_ctx_len=ctx,
        reason=reason,
        budget=budget,
    )


def _verdict(budget: VramBudget, ctx: int, model: ModelInfo) -> tuple[FitStatus, str]:
    estimated = " Size estimated from the model's name." if model.size_bytes is None else ""
    if not budget.fits:
        short = budget.total_required_mb - budget.vram_free_mb
        return "needs_offload", (
            f"Needs about {short} MB more VRAM than this card has free, so part of it would run "
            f"in system RAM and generation would be slow.{estimated}"
        )
    if budget.headroom_mb < 700:
        return "tight", (
            f"Fits at {ctx // 1024}K context with only {budget.headroom_mb} MB to spare - close "
            f"enough that another GPU-heavy window could push it over.{estimated}"
        )
    if ctx < 16384 and ctx < model.ctx_len_max:
        return "tight", (
            f"Fits, but this card holds only {ctx // 1024}K of its "
            f"{model.ctx_len_max // 1024}K context.{estimated}"
        )
    return "fits", (
        f"Fits fully on the GPU at {ctx // 1024}K context, with "
        f"{budget.headroom_mb} MB to spare.{estimated}"
    )


def rank(
    models: list[ModelInfo],
    *,
    gpu: GpuInfo | None,
    browser_reserve_mb: int,
    kv_dtype: str = "q8_0",
) -> list[ModelOption]:
    """Best first. Local models that fit outrank everything; remote is demoted below local."""
    options = [
        option_for(m, gpu=gpu, browser_reserve_mb=browser_reserve_mb, kv_dtype=kv_dtype)
        for m in models
    ]
    options.sort(
        key=lambda o: (
            o.remote,
            STATUS_ORDER[o.status],
            -(infer_params_b(o.model) or 0.0),
            o.model.display_name,
        )
    )
    for option in options:
        option.recommended = False
    if choice := best(options):
        choice.recommended = True
    return options


def best(options: list[ModelOption]) -> ModelOption | None:
    """The automatic pick: the largest local model that genuinely fits, else the least-bad local."""
    local = [o for o in options if not o.remote]
    if not local:
        return None
    for wanted in ("fits", "tight", "unavailable", "needs_offload"):
        if matches := [o for o in local if o.status == wanted]:
            return matches[0]
    return local[0]
