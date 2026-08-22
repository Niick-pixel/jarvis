"""`make bench`: measure the two numbers section 5.6 insists on measuring rather than assuming.

1. What the background costs in GPU time and VRAM while generation is running.
2. What the model actually generates, in tokens/sec, on this card.

The background measurement is a guided A/B rather than a fake automation: run it once with the
shader on, once with Performance mode on, and it reports the delta against the 3% budget. A
headless browser in WSL2 usually falls back to software rendering, which would make an automated
number confidently wrong - so it asks you instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.hardware import probe  # noqa: E402
from server.hardware.bench import bench  # noqa: E402
from server.providers.registry import ProviderRegistry  # noqa: E402
from server.settings import load_settings  # noqa: E402

SAMPLE_FILE = ROOT / "data" / "gpu_baseline.json"
BUDGET_PCT = 3.0


def sample(seconds: float) -> dict[str, float]:
    gpus, available = probe.probe_gpus()
    if not available or not gpus:
        raise SystemExit("No NVIDIA GPU visible, so there is nothing to measure here.")
    utilisation: list[float] = []
    used_mb: list[float] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current, _ = probe.probe_gpus()
        gpu = current[0]
        if gpu.utilization_pct is not None:
            utilisation.append(float(gpu.utilization_pct))
        used_mb.append(float(gpu.vram_used_mb))
        time.sleep(0.25)
    if not utilisation:
        raise SystemExit(
            "NVML did not expose GPU utilisation on this machine (common under WSL2), so the "
            "background cost cannot be measured here. Use Windows Task Manager's GPU graph "
            "instead, and compare shader-on against Performance mode."
        )
    return {
        "utilisation_mean": statistics.fmean(utilisation),
        "utilisation_p95": sorted(utilisation)[int(len(utilisation) * 0.95) - 1],
        "vram_used_mb": statistics.fmean(used_mb),
        "samples": len(utilisation),
    }


def background_ab(seconds: float) -> int:
    SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(SAMPLE_FILE.read_text()) if SAMPLE_FILE.exists() else None

    if baseline is None:
        print(
            "Step 1 of 2. Open the app with Performance mode ON (the shader is not running),\n"
            "start a generation, and leave it generating. Press Enter to sample for "
            f"{seconds:.0f}s."
        )
        input()
        result = sample(seconds)
        SAMPLE_FILE.write_text(json.dumps(result, indent=2))
        print(
            f"\nBaseline recorded: {result['utilisation_mean']:.1f}% GPU, "
            f"{result['vram_used_mb']:.0f} MB VRAM.\n"
            "Now turn Performance mode OFF so the shader runs, start another generation, "
            "and run `make bench` again."
        )
        return 0

    print(
        "Step 2 of 2. Open the app with Performance mode OFF (the shader is running),\n"
        f"start a generation, and leave it generating. Press Enter to sample for {seconds:.0f}s."
    )
    input()
    shader = sample(seconds)
    delta_pct = shader["utilisation_mean"] - baseline["utilisation_mean"]
    delta_vram = shader["vram_used_mb"] - baseline["vram_used_mb"]
    SAMPLE_FILE.unlink(missing_ok=True)

    print("\n--- background cost, measured ---")
    print(
        f"  without shader : {baseline['utilisation_mean']:.1f}% GPU, "
        f"{baseline['vram_used_mb']:.0f} MB VRAM"
    )
    print(
        f"  with shader    : {shader['utilisation_mean']:.1f}% GPU, "
        f"{shader['vram_used_mb']:.0f} MB VRAM"
    )
    print(f"  delta          : {delta_pct:+.1f}% GPU, {delta_vram:+.0f} MB VRAM")
    print(f"  budget         : {BUDGET_PCT:.0f}% GPU")
    if delta_pct > BUDGET_PCT:
        print(
            "\nOver budget. Section 5.6 says simplify the shader rather than ship it: drop an\n"
            "fBm octave in warp.frag, or lower BACKGROUND_DPR in perf.ts."
        )
        return 1
    print("\nWithin budget.")
    return 0


async def model_bench() -> int:
    settings = load_settings()
    registry = ProviderRegistry.from_settings(settings)
    try:
        provider, model = await registry.resolve(None)
    except Exception as exc:  # noqa: BLE001
        print(f"No backend reachable to bench: {exc}")
        return 1
    print(f"Benching {model.id} via {provider.name} ...")
    result = await bench(provider, model_id=model.id, ctx_len=model.ctx_len_max)
    print("  " + result.describe())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure background GPU cost and model speed.")
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--background-only", action="store_true")
    args = parser.parse_args()

    if args.model_only:
        return asyncio.run(model_bench())
    if args.background_only:
        return background_ab(args.seconds)
    code = asyncio.run(model_bench())
    return background_ab(args.seconds) or code


if __name__ == "__main__":
    raise SystemExit(main())
