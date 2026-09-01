"""Deciding what to serve, at what context, with which flags.

The model and the context length are chosen by the same arithmetic the picker and `make models`
use, so autostart cannot pick something the app would then call too big. Everything here is a pure
function of the settings, the database and the card - it starts nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from server.hardware import probe, recommend
from server.models.provider import ModelInfo
from server.settings import Settings

FALLBACK_CTX = 4096


def registered_models(conn: sqlite3.Connection, models_dir: Path) -> list[ModelInfo]:
    """GGUF files `make models` recorded, minus any that have since been deleted.

    This is the one reader of the `models` table: everywhere else the app asks a live backend what
    it is serving, which is no help when the question is what to serve.
    """
    rows = conn.execute(
        "SELECT id, display_name, file_path, sha256, quant, size_bytes, ctx_len_max"
        " FROM models WHERE provider = 'llamacpp' ORDER BY size_bytes DESC"
    )
    out: list[ModelInfo] = []
    for row in rows:
        path = Path(row["file_path"] or "")
        if not path.is_file():
            continue
        out.append(
            ModelInfo(
                id=row["id"],
                provider="llamacpp",
                display_name=row["display_name"] or path.name,
                file_path=str(path),
                sha256=row["sha256"] or "",
                quant=row["quant"],
                size_bytes=row["size_bytes"],
                ctx_len_max=row["ctx_len_max"] or 0,
                supports_logprobs=True,
                supports_prefix=True,
            )
        )
    if out:
        return out
    # Nothing registered: a file dropped into models_dir by hand is still a model.
    return [
        ModelInfo(
            id=f"llamacpp:{path.name}",
            provider="llamacpp",
            display_name=path.name,
            file_path=str(path),
            size_bytes=path.stat().st_size,
            ctx_len_max=0,
            supports_logprobs=True,
            supports_prefix=True,
        )
        for path in sorted(models_dir.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True)
    ]


def choose(models: list[ModelInfo], settings: Settings) -> tuple[ModelInfo | None, int]:
    """The largest model that fits this card, and the largest context it can hold with room."""
    if not models:
        return None, 0
    gpus, _ = probe.probe_gpus()
    gpu = gpus[0] if gpus else None
    reserve = settings.hardware.browser_vram_reserve_mb
    kv = settings.hardware.kv_cache_dtype
    best: tuple[ModelInfo, int] | None = None
    for model in models:
        ctx = recommend.max_ctx_for(model, gpu=gpu, browser_reserve_mb=reserve, kv_dtype=kv)
        if ctx and (best is None or (model.size_bytes or 0) > (best[0].size_bytes or 0)):
            best = (model, ctx)
    if best is None:
        # Nothing clears the margin. Serve the smallest at a modest context rather than refusing:
        # a slow model you can talk to beats a correct refusal at startup.
        smallest = min(models, key=lambda m: m.size_bytes or 0)
        return smallest, min(FALLBACK_CTX, smallest.ctx_len_max or FALLBACK_CTX)
    return best


def command(settings: Settings, model_path: str, ctx_len: int) -> list[str]:
    """The argv, matching what `make models` prints, plus whatever you added in extra_args."""
    cfg = settings.providers.llamacpp
    url = urlparse(cfg.base_url)
    gpus, _ = probe.probe_gpus()
    kv = settings.hardware.kv_cache_dtype
    argv = [
        cfg.binary,
        "--model",
        model_path,
        "--ctx-size",
        str(ctx_len),
        "--host",
        url.hostname or "127.0.0.1",
        "--port",
        str(url.port or 8081),
        "--cache-type-k",
        kv,
        "--cache-type-v",
        kv,
    ]
    if gpus:
        argv += ["-ngl", "999"]
        if kv != "f16":
            # A quantised V cache needs flash attention in every recent build; without this the
            # server exits at startup with a message most people read as "quantisation is broken".
            argv.append("--flash-attn")
    return argv + list(cfg.extra_args)
