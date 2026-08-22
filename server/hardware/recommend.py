"""The VRAM arithmetic. One implementation, used by both `make models` and the preflight check.

Everything here is stated as a formula rather than a lookup table so you can check the numbers
against your own card instead of trusting them (PLAN.md 1.1).
"""

from __future__ import annotations

from server.errors import Remedy
from server.models.hardware import GpuInfo, VramBudget
from server.models.provider import ModelInfo

MB = 1024 * 1024
CTX_STEPS = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144]

# Effective bits per weight, including the mixed-precision tensors real GGUFs carry.
QUANT_BITS: dict[str, float] = {
    "Q3_K_M": 3.9,
    "Q4_K_M": 4.85,
    "Q4_0": 4.55,
    "MXFP4": 4.25,
    "Q5_K_M": 5.7,
    "Q6_K": 6.6,
    "Q8_0": 8.5,
    "F16": 16.0,
}
KV_DTYPE_BYTES = {"f16": 2, "q8_0": 1}

# A dense 7-9B model's graph buffers at a normal batch size. An estimate, and labelled as one.
COMPUTE_BUFFER_MB = 400


def kv_cache_mb(
    *, n_layers: int, n_kv_heads: int, head_dim: int, ctx_len: int, kv_dtype: str = "q8_0"
) -> int:
    """2 (K and V) x layers x kv_heads x head_dim x ctx x bytes-per-element."""
    per_element = KV_DTYPE_BYTES.get(kv_dtype, 2)
    total = 2 * n_layers * n_kv_heads * head_dim * ctx_len * per_element
    return round(total / MB)


def weights_mb(*, size_bytes: int | None, params_b: float | None, quant: str | None) -> int:
    """Prefer the real file size; fall back to params x effective bits when it is not downloaded."""
    if size_bytes:
        return round(size_bytes / MB)
    if params_b:
        bits = QUANT_BITS.get((quant or "Q4_K_M").upper(), 4.85)
        return round(params_b * 1e9 * bits / 8 / MB)
    return 0


def _fallback_geometry(params_b: float) -> tuple[int, int, int]:
    """When GGUF metadata is missing, use the shape 7-9B GQA models converged on, and say so."""
    if params_b <= 4:
        return 28, 4, 128
    if params_b <= 10:
        return 32, 8, 128
    if params_b <= 16:
        return 40, 8, 128
    return 48, 8, 128


def budget_for(
    model: ModelInfo,
    *,
    ctx_len: int,
    gpu: GpuInfo | None,
    browser_reserve_mb: int,
    kv_dtype: str = "q8_0",
    params_b: float | None = None,
) -> VramBudget:
    layers = model.n_layers
    kv_heads = model.n_kv_heads
    head_dim = model.head_dim
    estimated_geometry = not (layers and kv_heads and head_dim)
    if estimated_geometry:
        layers, kv_heads, head_dim = _fallback_geometry(params_b or 8.0)
    kv = kv_cache_mb(
        n_layers=layers or 32,
        n_kv_heads=kv_heads or 8,
        head_dim=head_dim or 128,
        ctx_len=ctx_len,
        kv_dtype=kv_dtype,
    )
    weights = weights_mb(size_bytes=model.size_bytes, params_b=params_b, quant=model.quant)
    total = weights + kv + COMPUTE_BUFFER_MB + browser_reserve_mb
    vram_total = gpu.vram_total_mb if gpu else 0
    vram_free = gpu.vram_free_mb if gpu else 0
    fits = bool(gpu) and total <= vram_free
    headroom = vram_free - total
    return VramBudget(
        model_id=model.id,
        ctx_len=ctx_len,
        kv_dtype=kv_dtype,  # type: ignore[arg-type]
        weights_mb=weights,
        kv_cache_mb=kv,
        compute_buffer_mb=COMPUTE_BUFFER_MB,
        browser_reserve_mb=browser_reserve_mb,
        total_required_mb=total,
        vram_total_mb=vram_total,
        vram_free_mb=vram_free,
        fits=fits,
        headroom_mb=headroom,
        explanation=_explain(
            model,
            ctx_len,
            weights,
            kv,
            browser_reserve_mb,
            total,
            vram_free,
            gpu,
            estimated_geometry,
        ),
        remedy=None if fits else _remedy(model, ctx_len, kv, headroom),
    )


def _explain(
    model: ModelInfo,
    ctx_len: int,
    weights: int,
    kv: int,
    browser: int,
    total: int,
    free: int,
    gpu: GpuInfo | None,
    estimated_geometry: bool,
) -> str:
    if gpu is None:
        return (
            f"No GPU detected, so {model.display_name} would run on CPU. "
            f"It needs about {weights} MB of weights plus {kv} MB of KV cache at {ctx_len} tokens."
        )
    caveat = " Layer geometry estimated from parameter count." if estimated_geometry else ""
    return (
        f"{model.display_name} at {ctx_len} tokens: {weights} MB weights + {kv} MB KV cache "
        f"+ {COMPUTE_BUFFER_MB} MB compute buffers (estimate) + {browser} MB reserved for the "
        f"browser's GPU process = {total} MB against {free} MB free of "
        f"{gpu.vram_total_mb} MB.{caveat}"
    )


def _remedy(model: ModelInfo, ctx_len: int, kv: int, headroom: int) -> Remedy:
    smaller = max((c for c in CTX_STEPS if c < ctx_len), default=None)
    if smaller:
        return Remedy(
            label=f"Drop context to {smaller // 1024}K",
            action="reduce_context",
            params={"ctx_len": smaller, "model_id": model.id},
        )
    return Remedy(
        label="Choose a smaller model",
        action="choose_model",
        params={"shortfall_mb": max(0, -headroom)},
    )


def max_ctx_for(
    model: ModelInfo,
    *,
    gpu: GpuInfo | None,
    browser_reserve_mb: int,
    kv_dtype: str = "q8_0",
    params_b: float | None = None,
    safety_margin_mb: int = 512,
) -> int:
    """The largest context this card can hold with room to breathe.

    Largest-that-technically-fits is the wrong default: a context that leaves 50 MB spare dies the
    first time you open a second browser tab. We keep a margin, and fall back to the absolute
    ceiling only when nothing clears it.
    """
    best = 0
    absolute = 0
    for ctx in CTX_STEPS:
        if ctx > model.ctx_len_max:
            break
        budget = budget_for(
            model,
            ctx_len=ctx,
            gpu=gpu,
            browser_reserve_mb=browser_reserve_mb,
            kv_dtype=kv_dtype,
            params_b=params_b,
        )
        if budget.fits:
            absolute = ctx
            if budget.headroom_mb >= safety_margin_mb:
                best = ctx
    return best or absolute or min(CTX_STEPS[0], model.ctx_len_max)
