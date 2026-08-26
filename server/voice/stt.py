"""Speech to text with faster-whisper, loaded once and never downloaded implicitly.

The model is held in memory between clips because loading `small` costs about a second, and a
push-to-talk button that pauses for a second on every press is a button nobody uses. It is loaded
on first use rather than at startup, so a text-only session never pays for it at all.
"""

from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass
from typing import Any

from server.models.voice import Transcript
from server.settings import Settings
from server.voice import capability
from server.voice.capability import VoiceUnavailable


@dataclass
class Engine:
    model: Any
    model_id: str
    device: str
    compute_type: str


_engine: Engine | None = None
_lock = asyncio.Lock()
"""One clip at a time. CTranslate2 with a single worker is not a place to send concurrent work."""


def loaded_device() -> str:
    """What the model actually loaded onto, so the status endpoint reports fact, not intent."""
    return _engine.device if _engine else ""


def unload() -> None:
    """Give the VRAM back. Used by the tests and by anything that needs the card for tokens."""
    global _engine
    _engine = None


def _load(settings: Settings) -> Engine:
    status = capability.stt_status(settings)
    if not status.available:
        raise VoiceUnavailable(status.reason, status.fix)
    from faster_whisper import WhisperModel

    plan = capability.stt_plan(settings)
    try:
        model = WhisperModel(
            str(plan.model_dir),
            device=plan.device,
            compute_type=plan.compute_type,
            local_files_only=True,
        )
        return Engine(model, plan.model_id, plan.device, plan.compute_type)
    except Exception as exc:  # noqa: BLE001 - no CUDA runtime, wrong compute type, corrupt weights
        if plan.device != "cuda":
            raise VoiceUnavailable(
                f"Whisper failed to load from {plan.model_dir}: {exc}",
                "Re-run `make voice` to fetch the files again.",
            ) from exc
        # A card NVML can see is not the same as a CUDA runtime CTranslate2 can use. Falling back
        # to CPU is better than refusing, as long as the status says so afterwards.
        model = WhisperModel(
            str(plan.model_dir), device="cpu", compute_type="int8", local_files_only=True
        )
        return Engine(model, plan.model_id, "cpu", "int8")


async def engine(settings: Settings) -> Engine:
    global _engine
    async with _lock:
        if _engine is None:
            _engine = await asyncio.to_thread(_load, settings)
        return _engine


def _run(engine: Engine, audio: bytes, language: str) -> Transcript:
    started = time.perf_counter()
    segments, info = engine.model.transcribe(
        io.BytesIO(audio),
        language=language or None,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    # `segments` is lazy: the work happens here, inside the worker thread, not at the caller.
    text = "".join(segment.text for segment in segments).strip()
    return Transcript(
        text=text,
        language=info.language or "",
        language_probability=round(info.language_probability or 0.0, 3),
        audio_seconds=round(info.duration or 0.0, 2),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        device=engine.device,
    )


async def transcribe(settings: Settings, audio: bytes) -> Transcript:
    """Decode and transcribe one clip. Whatever the browser recorded, PyAV can read."""
    limit = settings.voice.max_audio_mb * 1024 * 1024
    if len(audio) > limit:
        raise ValueError(
            f"Clip is {len(audio) / 1e6:.1f}MB, over the {settings.voice.max_audio_mb}MB limit."
        )
    if not audio:
        raise ValueError("Empty clip: the recorder produced no audio.")
    loaded = await engine(settings)
    async with _lock:
        try:
            return await asyncio.to_thread(_run, loaded, audio, settings.voice.stt_language)
        except VoiceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - undecodable container, truncated upload
            raise ValueError(f"Could not decode that audio: {exc}") from exc
