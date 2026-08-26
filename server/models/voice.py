"""Voice: what the machine can actually do, and why it cannot do the rest (BRIEF.md 5.3, 8).

Every field here exists so the UI can state a limitation instead of showing a dead button.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EngineStatus(BaseModel):
    role: Literal["stt", "tts"]
    engine: str
    """`faster-whisper` or `piper`. Named so the reason below is attributable."""
    available: bool
    model_id: str = ""
    device: str = ""
    """Where it would run, or did run: `cuda` or `cpu`. Empty when it cannot run at all."""
    compute_type: str = ""
    vram_estimate_mb: int = 0
    """Rough cost of holding this model, so it can be printed next to the choice (PLAN.md 1.5).
    Zero on CPU, where it costs system RAM instead and the GPU stays free for tokens."""
    expected_path: str = ""
    """Exactly where the files must be. Nothing is fetched behind your back."""
    reason: str = ""
    """Plain English, present tense, no jargon: why this engine is unavailable right now."""
    fix: str = ""
    """The one command that changes the answer. Empty when there is nothing you can run."""


class VoiceStatus(BaseModel):
    stt: EngineStatus
    tts: EngineStatus
    voices: list[str] = []
    """Piper voices actually present on disk, not a catalogue of what exists."""


class Transcript(BaseModel):
    text: str
    language: str = ""
    language_probability: float = 0.0
    audio_seconds: float = 0.0
    elapsed_ms: int = 0
    device: str = ""
    """What it really ran on. A CUDA plan that fell back to CPU says `cpu` here."""


class SpeakRequest(BaseModel):
    text: str
    voice: str | None = None
    """One of `VoiceStatus.voices`. None uses the configured default."""
