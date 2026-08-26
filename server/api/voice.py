"""Local speech in and out. Both engines are optional, and say so rather than failing silently."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from server.deps import State
from server.errors import SovereignError
from server.models.voice import SpeakRequest, Transcript, VoiceStatus
from server.voice import capability, stt, tts
from server.voice.capability import VoiceUnavailable

router = APIRouter(prefix="/api/voice", tags=["voice"])

WAV_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "description": "A WAV stream, one PCM block per sentence.",
        "content": {"audio/wav": {}},
    }
}


@router.get("/status")
def status(state: State) -> VoiceStatus:
    """Which half of voice works, on what device, and the exact command that fixes the rest."""
    return capability.status(state.settings, stt_device=stt.loaded_device())


@router.post("/transcribe")
async def transcribe(request: Request, state: State) -> Transcript:
    """The raw recording as the request body. Whatever the browser captured, PyAV decodes.

    Taking bytes rather than a multipart form is not laziness: multipart would pull in another
    dependency to carry one field.
    """
    audio = await request.body()
    try:
        return await stt.transcribe(state.settings, audio)
    except VoiceUnavailable as exc:
        raise _unavailable(exc) from exc
    except ValueError as exc:
        raise SovereignError("invalid_request", str(exc)) from exc


@router.post("/speak", responses=WAV_RESPONSES)
async def speak(body: SpeakRequest, state: State) -> StreamingResponse:
    if not body.text.strip():
        raise SovereignError("invalid_request", "Nothing to speak.")
    try:
        # Resolve the voice before the response begins: once bytes are on the wire an error can
        # only be a truncated stream, which sounds like a bug rather than reading like one.
        await tts.voice_for(state.settings, body.voice)
    except VoiceUnavailable as exc:
        raise _unavailable(exc) from exc
    return StreamingResponse(
        tts.stream_wav(state.settings, body.text, body.voice),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


def _unavailable(exc: VoiceUnavailable) -> SovereignError:
    detail = f"{exc.reason} Fix: {exc.fix}" if exc.fix else exc.reason
    return SovereignError("provider_unavailable", detail, status_code=503)
