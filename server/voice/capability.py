"""Can this machine speak and listen, and if not, what exactly is missing.

Two things can be absent independently: the Python package (voice is an optional extra, because a
text-only install has no reason to carry an ONNX runtime) and the model weights (never downloaded
implicitly). Each produces a different sentence and a different fix, and the UI prints both rather
than disabling a button with no explanation.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from server.hardware import probe
from server.models.voice import EngineStatus, VoiceStatus
from server.settings import Settings

# Whisper parameter counts, in millions. The VRAM estimate below is arithmetic on these rather
# than a number copied from a blog post, and it is labelled an estimate everywhere it is shown.
WHISPER_PARAMS_M = {
    "tiny": 39,
    "tiny.en": 39,
    "base": 74,
    "base.en": 74,
    "small": 244,
    "small.en": 244,
    "medium": 769,
    "medium.en": 769,
    "large-v2": 1550,
    "large-v3": 1550,
    "distil-large-v3": 756,
}
BYTES_PER_PARAM = {"int8": 1, "int8_float16": 1, "float16": 2, "float32": 4}
ACTIVATION_OVERHEAD_MB = 200
"""Encoder activations and the CT2 workspace. Measured range is 150-250MB at these sizes."""

INSTALL_FIX = "make voice-install"
DOWNLOAD_FIX = "make voice"


class VoiceUnavailable(RuntimeError):
    """Carries the sentence built here verbatim, so one explanation reaches the user."""

    def __init__(self, reason: str, fix: str = "") -> None:
        super().__init__(f"{reason} {fix}".strip() if fix else reason)
        self.reason = reason
        self.fix = fix


@dataclass(frozen=True)
class SttPlan:
    """What `stt` will attempt. Separate from the status so the two agree by construction."""

    model_dir: Path
    model_id: str
    device: str
    compute_type: str


def stt_plan(settings: Settings) -> SttPlan:
    model_id = settings.voice.stt_model
    gpus, _ = probe.probe_gpus()
    device = "cuda" if gpus else "cpu"
    # int8_float16 is a CUDA-only pairing; asking for it on CPU raises inside CTranslate2.
    compute = settings.voice.stt_compute_type if device == "cuda" else "int8"
    return SttPlan(whisper_dir(settings, model_id), model_id, device, compute)


def whisper_dir(settings: Settings, model_id: str) -> Path:
    return settings.paths.models_dir / "whisper" / model_id


def piper_dir(settings: Settings) -> Path:
    return settings.paths.models_dir / "piper"


def voice_files(settings: Settings, name: str) -> tuple[Path, Path]:
    """Piper needs the ONNX graph and the JSON beside it; one without the other is not a voice."""
    base = piper_dir(settings) / f"{name}.onnx"
    return base, base.with_suffix(".onnx.json")


def installed_voices(settings: Settings) -> list[str]:
    folder = piper_dir(settings)
    if not folder.is_dir():
        return []
    names = [p.name[: -len(".onnx")] for p in sorted(folder.glob("*.onnx"))]
    return [n for n in names if voice_files(settings, n)[1].is_file()]


def vram_estimate_mb(model_id: str, compute_type: str, device: str) -> int:
    if device != "cuda":
        return 0
    params = WHISPER_PARAMS_M.get(model_id)
    if params is None:
        return 0
    return round(params * BYTES_PER_PARAM.get(compute_type, 1) + ACTIVATION_OVERHEAD_MB)


def stt_status(settings: Settings, *, actual_device: str = "") -> EngineStatus:
    plan = stt_plan(settings)
    device = actual_device or plan.device
    status = EngineStatus(
        role="stt",
        engine="faster-whisper",
        available=False,
        model_id=plan.model_id,
        device=device,
        compute_type=plan.compute_type,
        vram_estimate_mb=vram_estimate_mb(plan.model_id, plan.compute_type, device),
        expected_path=str(plan.model_dir),
    )
    if find_spec("faster_whisper") is None:
        return status.model_copy(
            update={
                "device": "",
                "vram_estimate_mb": 0,
                "reason": "faster-whisper is not installed. Voice is an optional extra so a "
                "text-only install does not carry an ONNX runtime it never uses.",
                "fix": INSTALL_FIX,
            }
        )
    if not (plan.model_dir / "model.bin").is_file():
        return status.model_copy(
            update={
                "reason": f"No Whisper model at {plan.model_dir}. Nothing is downloaded until "
                "you ask for it.",
                "fix": DOWNLOAD_FIX,
            }
        )
    return status.model_copy(update={"available": True})


def tts_status(settings: Settings) -> EngineStatus:
    name = settings.voice.tts_voice
    onnx, config = voice_files(settings, name)
    status = EngineStatus(
        role="tts",
        engine="piper",
        available=False,
        model_id=name,
        device="cpu",
        compute_type="int16 pcm",
        # Piper runs on CPU on purpose: the GPU is for tokens (PLAN.md 1.5).
        vram_estimate_mb=0,
        expected_path=str(onnx),
    )
    if find_spec("piper") is None:
        return status.model_copy(
            update={
                "device": "",
                "reason": "piper-tts is not installed. Voice is an optional extra.",
                "fix": INSTALL_FIX,
            }
        )
    if not onnx.is_file():
        return status.model_copy(update={"reason": f"No voice at {onnx}.", "fix": DOWNLOAD_FIX})
    if not config.is_file():
        return status.model_copy(
            update={
                "reason": f"{onnx.name} is present but {config.name} is missing; Piper needs both.",
                "fix": DOWNLOAD_FIX,
            }
        )
    return status.model_copy(update={"available": True})


def status(settings: Settings, *, stt_device: str = "") -> VoiceStatus:
    return VoiceStatus(
        stt=stt_status(settings, actual_device=stt_device),
        tts=tts_status(settings),
        voices=installed_voices(settings),
    )
