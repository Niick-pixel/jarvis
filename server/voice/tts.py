"""Text to speech with Piper, on the CPU, streamed a sentence at a time.

Piper synthesises a whole utterance at once, so "streaming" here means the text is cut into
sentences and each one is sent as soon as it exists: you hear the first clause while the third is
still being rendered. The tradeoff is a WAV header written before the length is known, which means
the player gets audio immediately but shows no duration and cannot scrub.
"""

from __future__ import annotations

import asyncio
import re
import struct
from collections.abc import AsyncIterator
from typing import Any

from server.settings import Settings
from server.voice import capability
from server.voice.capability import VoiceUnavailable

UNKNOWN_LENGTH = 0xFFFFFFFF
"""RIFF has no way to say "I don't know yet"; the maximum is the convention for a live stream."""
MAX_SENTENCE_CHARS = 320
SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+|\n+")
CLAUSE_END = re.compile(r"(?<=,)\s+|\s+")

_voices: dict[str, Any] = {}
_lock = asyncio.Lock()


def unload() -> None:
    _voices.clear()


def wav_header(sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    """A 44-byte canonical header with both sizes left open (see the module docstring)."""
    block_align = channels * bits // 8
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", UNKNOWN_LENGTH),
            b"WAVEfmt ",
            struct.pack(
                "<IHHIIHH",
                16,
                1,
                channels,
                sample_rate,
                sample_rate * block_align,
                block_align,
                bits,
            ),
            b"data",
            struct.pack("<I", UNKNOWN_LENGTH),
        )
    )


def sentences(text: str) -> list[str]:
    """Cut on sentence ends, then on clause ends, so no single synthesis call runs long."""
    out: list[str] = []
    for part in SENTENCE_END.split(text.strip()):
        piece = part.strip()
        if not piece:
            continue
        while len(piece) > MAX_SENTENCE_CHARS:
            head, piece = _split_once(piece)
            out.append(head)
        out.append(piece)
    return out


def _split_once(piece: str) -> tuple[str, str]:
    cut = 0
    for match in CLAUSE_END.finditer(piece):
        if match.start() > MAX_SENTENCE_CHARS:
            break
        cut = match.start()
    if cut == 0:
        cut = MAX_SENTENCE_CHARS
    return piece[:cut].strip(), piece[cut:].strip()


def _load(settings: Settings, name: str) -> Any:
    status = capability.tts_status(settings)
    if not status.available:
        raise VoiceUnavailable(status.reason, status.fix)
    from piper import PiperVoice

    onnx, config = capability.voice_files(settings, name)
    if not onnx.is_file():
        raise VoiceUnavailable(f"No voice at {onnx}.", capability.DOWNLOAD_FIX)
    return PiperVoice.load(onnx, config_path=config, use_cuda=False)


async def voice_for(settings: Settings, name: str | None = None) -> tuple[str, Any]:
    chosen = name or settings.voice.tts_voice
    async with _lock:
        if chosen not in _voices:
            _voices[chosen] = await asyncio.to_thread(_load, settings, chosen)
        return chosen, _voices[chosen]


def _synthesize(voice: Any, text: str, length_scale: float) -> bytes:
    from piper import SynthesisConfig

    config = SynthesisConfig(length_scale=length_scale)
    return b"".join(chunk.audio_int16_bytes for chunk in voice.synthesize(text, config))


async def stream_wav(
    settings: Settings, text: str, name: str | None = None
) -> AsyncIterator[bytes]:
    """Yields a WAV header, then one PCM block per sentence, in order."""
    spoken = text.strip()
    if not spoken:
        raise ValueError("Nothing to speak.")
    _, voice = await voice_for(settings, name)
    yield wav_header(voice.config.sample_rate)
    for sentence in sentences(spoken):
        yield await asyncio.to_thread(_synthesize, voice, sentence, settings.voice.tts_length_scale)
