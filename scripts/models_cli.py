"""`make models`: read the real card, rank what fits, download the one you pick, then bench it.

No tags are hardcoded (see PLAN.md 1.2). Sizes come from the registry and tokens/sec is measured
on your hardware after the download, because a number copied from someone else's benchmark is
worse than no number.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.hardware import catalog as catalog_mod  # noqa: E402
from server.hardware import probe  # noqa: E402
from server.models.hardware import ModelRecommendation  # noqa: E402
from server.settings import load_settings  # noqa: E402

CATALOG = ROOT / "models.toml"
STATUS_LABEL = {
    "fits": "fits",
    "tight": "tight",
    "needs_offload": "too big",
    "unavailable": "n/a",
}


def resolve_file(entry: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    """Ask the registry for the real filename, byte size and hash. Offline is not fatal."""
    try:
        from fnmatch import fnmatch

        from huggingface_hub import HfApi

        info = HfApi().model_info(entry["hf_repo"], files_metadata=True)
        matches = [s for s in info.siblings if fnmatch(s.rfilename, entry["file_glob"])]
        if not matches:
            return None, None, None
        best = min(matches, key=lambda s: s.size or 0)
        sha = getattr(best, "lfs", None)
        return best.rfilename, best.size, getattr(sha, "sha256", None)
    except Exception:  # noqa: BLE001 - offline, rate limited, or the repo moved
        return None, None, None


def print_table(rows: list[tuple[ModelRecommendation, str | None, int | None]]) -> None:
    print(f"\n{'#':>2}  {'model':<26} {'status':<8} {'size':>8}  {'ctx':>7}  note")
    print("-" * 108)
    for index, (rec, filename, size) in enumerate(rows, start=1):
        size_text = f"{size / 1e9:.1f} GB" if size else "unknown"
        ctx = f"{rec.recommended_ctx_len // 1024}K" if rec.recommended_ctx_len else "-"
        marker = " *" if rec.installed else "  "
        print(
            f"{index:>2}{marker}{rec.display_name:<26} {STATUS_LABEL[rec.status]:<8} "
            f"{size_text:>8}  {ctx:>7}  {rec.note}"
        )
        if filename is None:
            print(f"      could not resolve {rec.key} in the registry (offline, or the repo moved)")
        elif rec.why:
            print(f"      {rec.why}")


def installed_keys(models_dir: Path) -> set[str]:
    if not models_dir.is_dir():
        return set()
    present = {p.name.lower() for p in models_dir.glob("*.gguf")}
    keys: set[str] = set()
    for entry in catalog_mod.load_catalog(CATALOG):
        stem = entry["key"].replace("-", "").replace(".", "")
        if any(stem[:6] in name.replace("-", "").replace(".", "") for name in present):
            keys.add(entry["key"])
    return keys


def download(entry: dict[str, Any], filename: str, size: int | None, models_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download

    models_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(models_dir).free
    if size and size > free:
        raise SystemExit(
            f"Not enough disk: {filename} needs {size / 1e9:.1f} GB, "
            f"{free / 1e9:.1f} GB free in {models_dir}."
        )
    print(f"\nDownloading {filename} into {models_dir} ...")
    path = hf_hub_download(repo_id=entry["hf_repo"], filename=filename, local_dir=str(models_dir))
    return Path(path)


def register(path: Path, entry: dict[str, Any], sha256: str | None, ctx_len: int) -> None:
    """Record the file so the app can show it, and so a rerun can verify the exact weights."""
    from server.db.connection import Database

    settings = load_settings()
    db = Database(settings.paths.db_path)
    with db.session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO models (id, provider, display_name, file_path, sha256, quant,"
            " size_bytes, ctx_len_max, supports_logprobs, supports_prefix, last_seen_at)"
            " VALUES (?,?,?,?,?,?,?,?,1,1,strftime('%s','now')*1000)",
            (
                f"llamacpp:{path.name}",
                "llamacpp",
                entry["display_name"],
                str(path),
                sha256 or "",
                entry.get("quant"),
                path.stat().st_size,
                ctx_len,
            ),
        )


def next_steps(path: Path, ctx_len: int) -> None:
    print(
        "\nDone. Start the backend with:\n"
        f"  llama-server --model {path} --ctx-size {ctx_len} \\\n"
        "      --host 127.0.0.1 --port 8081 --cache-type-k q8_0 --cache-type-v q8_0 -ngl 999\n"
        "\nThen `make bench` measures the real tokens/sec on this card, and `make dev` starts the"
        " app.\nThe loopback bind is deliberate: never expose the inference port off-box."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank and download a model that fits this card.")
    parser.add_argument("--json", action="store_true", help="print the ranking as JSON and exit")
    parser.add_argument("--pick", type=int, help="skip the prompt and take this row number")
    args = parser.parse_args()

    settings = load_settings()
    report = probe.report(settings.paths.models_dir)
    gpu = report.gpus[0] if report.gpus else None

    # With --json, stdout must be nothing but JSON so it can be piped.
    log = sys.stderr if args.json else sys.stdout
    if gpu:
        print(f"GPU: {gpu.name} - {gpu.vram_free_mb} MB free of {gpu.vram_total_mb} MB", file=log)
    else:
        print("No NVIDIA GPU visible: ranking for CPU, which will be slow but will work.", file=log)
    print(
        f"Reserving {settings.hardware.browser_vram_reserve_mb} MB for the browser's GPU process, "
        f"and using a {settings.hardware.kv_cache_dtype} KV cache.",
        file=log,
    )
    for note in report.notes:
        print(f"  note: {note}", file=log)

    entries = catalog_mod.load_catalog(CATALOG)
    ranked = catalog_mod.rank_catalog(
        entries,
        gpu=gpu,
        browser_reserve_mb=settings.hardware.browser_vram_reserve_mb,
        kv_dtype=settings.hardware.kv_cache_dtype,
        installed=installed_keys(settings.paths.models_dir),
    )
    by_key = {e["key"]: e for e in entries}
    rows = [(rec, *resolve_file(by_key[rec.key])[:2]) for rec in ranked]

    if args.json:
        print(json.dumps([r.model_dump() for r in ranked], indent=2))
        return 0

    print_table(rows)
    choice = args.pick
    if choice is None:
        raw = input("\nDownload which? (number, or blank to exit) ").strip()
        if not raw:
            return 0
        choice = int(raw)
    if not 1 <= choice <= len(rows):
        raise SystemExit(f"No row {choice}")

    rec = rows[choice - 1][0]
    entry = by_key[rec.key]
    filename, size, sha256 = resolve_file(entry)
    if filename is None:
        raise SystemExit(f"Cannot resolve a file for {rec.key} right now.")
    if rec.status == "needs_offload":
        print(f"\n{rec.display_name} does not fit this card: {rec.note}")
        if input("Download anyway and run partly on CPU? [y/N] ").strip().lower() != "y":
            return 0

    path = download(entry, filename, size, settings.paths.models_dir)
    register(path, entry, sha256, rec.recommended_ctx_len)
    next_steps(path, rec.recommended_ctx_len)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
