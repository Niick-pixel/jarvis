"""`make voice`: fetch the speech models, into the paths the app already looks in.

Nothing here runs at startup and nothing runs on a request. Voice weights arrive when you type
this command and never otherwise, which is the whole point of a local-first workspace.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.models.voice import EngineStatus  # noqa: E402
from server.settings import load_settings  # noqa: E402
from server.voice import capability  # noqa: E402

WHISPER_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base": "Systran/faster-whisper-base",
    "base.en": "Systran/faster-whisper-base.en",
    "small": "Systran/faster-whisper-small",
    "small.en": "Systran/faster-whisper-small.en",
    "medium": "Systran/faster-whisper-medium",
    "medium.en": "Systran/faster-whisper-medium.en",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
}
WHISPER_FILES = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]
PIPER_REPO = "rhasspy/piper-voices"


def piper_paths(name: str) -> tuple[str, str]:
    """`en_US-lessac-medium` lives at `en/en_US/lessac/medium/` in the voices repo."""
    try:
        locale, speaker, quality = name.split("-")
        language = locale.split("_")[0]
    except ValueError as exc:
        raise SystemExit(f"Voice name {name!r} is not <locale>-<speaker>-<quality>.") from exc
    folder = f"{language}/{locale}/{speaker}/{quality}"
    return f"{folder}/{name}.onnx", f"{folder}/{name}.onnx.json"


def print_status(status: EngineStatus) -> None:
    mark = "ok " if status.available else "-- "
    cost = f"  ~{status.vram_estimate_mb}MB VRAM" if status.vram_estimate_mb else ""
    device = f" on {status.device}" if status.device else ""
    print(f"{mark}{status.role}: {status.engine} {status.model_id}{device}{cost}")
    print(f"    {status.expected_path}")
    if status.reason:
        print(f"    {status.reason}")
        if status.fix:
            print(f"    fix: {status.fix}")


def fetch(repo: str, filename: str, target: Path) -> Path:
    from huggingface_hub import hf_hub_download

    target.parent.mkdir(parents=True, exist_ok=True)
    cached = hf_hub_download(repo_id=repo, filename=filename)
    data = Path(cached).read_bytes()
    target.write_bytes(data)
    print(f"    {target.name:<24} {len(data) / 1e6:8.1f} MB")
    return target


def download_stt(settings: object, model_id: str) -> None:
    repo = WHISPER_REPOS.get(model_id)
    if repo is None:
        raise SystemExit(
            f"No known CTranslate2 repo for {model_id!r}. Known: {', '.join(WHISPER_REPOS)}"
        )
    target = capability.whisper_dir(settings, model_id)  # type: ignore[arg-type]
    print(f"\nSTT  {repo} -> {target}")
    for filename in WHISPER_FILES:
        try:
            fetch(repo, filename, target / filename)
        except Exception as exc:  # noqa: BLE001 - optional files differ between sizes
            if filename in ("model.bin", "config.json"):
                raise SystemExit(_network_hint(repo, filename, exc)) from exc
            print(f"    {filename:<24} not in this repo, skipped")


def download_tts(settings: object, name: str) -> None:
    onnx_path, config_path = piper_paths(name)
    onnx, config = capability.voice_files(settings, name)  # type: ignore[arg-type]
    print(f"\nTTS  {PIPER_REPO} -> {onnx.parent}")
    for remote, local in ((onnx_path, onnx), (config_path, config)):
        try:
            fetch(PIPER_REPO, remote, local)
        except Exception as exc:  # noqa: BLE001 - offline, blocked, or a name that does not exist
            raise SystemExit(_network_hint(PIPER_REPO, remote, exc)) from exc


def _network_hint(repo: str, filename: str, exc: Exception) -> str:
    """A download that cannot happen says where the bytes live, so you can carry them in."""
    return (
        f"\n    could not fetch {filename} from {repo}: {exc}\n"
        f"    direct URL: https://huggingface.co/{repo}/resolve/main/{filename}\n"
        "    Download it however you like and drop it at the path printed above; the app only\n"
        "    ever looks at the filesystem."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status", action="store_true", help="print what is present, download nothing"
    )
    parser.add_argument("--stt-only", action="store_true")
    parser.add_argument("--tts-only", action="store_true")
    parser.add_argument("--model", default="", help="Whisper size (default: config.toml)")
    parser.add_argument("--voice", default="", help="Piper voice (default: config.toml)")
    args = parser.parse_args()

    settings = load_settings()
    model_id = args.model or settings.voice.stt_model
    voice_name = args.voice or settings.voice.tts_voice

    status = capability.status(settings)
    print("Voice, as it stands:\n")
    print_status(status.stt)
    print_status(status.tts)
    if status.voices:
        print(f"\ninstalled voices: {', '.join(status.voices)}")
    if args.status:
        return 0

    if not args.tts_only:
        download_stt(settings, model_id)
    if not args.stt_only:
        download_tts(settings, voice_name)

    after = capability.status(settings)
    print("\nAfter downloading:\n")
    print_status(after.stt)
    print_status(after.tts)
    if not (after.stt.available and after.tts.available):
        return 1
    print("\nBoth engines are ready. The mic button in the composer is now live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
