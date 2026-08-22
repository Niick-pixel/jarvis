"""Verify body text clears 4.5:1 against the brightest frame the shader can actually produce.

Section 5.5 says to test the shader's real extremes rather than a screenshot, because a screenshot
only proves one frame was fine. The mesh gradient makes that provable rather than sampled:

  * The colour is `(uBase + sum(w_i * uColors[i])) / (1 + sum(w_i))` with every `w_i >= 0` - a
    convex combination. Its luminance therefore cannot exceed the brightest of those colours,
    whatever the noise, the blob positions or the pointer do.
  * The only things applied afterwards are a bounded gain (the status sweep and the token pulse),
    a desaturating error mix, and a hard luminance clamp.

So the brightest producible luminance is exactly `min(maxLuma, brightest_colour * max_gain)`, and
this checks the text against that. It reads the palette from presets.json - the same file the app
renders from - so the check cannot validate a palette that is not on screen.

If it fails, the fix is to darken the palette or the scrim, not to relax the target.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS_JSON = ROOT / "web" / "src" / "scene" / "presets.json"
FRAG = ROOT / "web" / "src" / "scene" / "shaders" / "mesh.frag"

# `col *= 1.0 + 0.07 * uEnergy * sweep + 0.10 * uPulse`, with uEnergy, sweep and uPulse all <= 1.
MAX_GAIN = 1.0 + 0.07 + 0.10
DITHER = 0.5 / 512  # `col += (hash(...) - 0.5) * (1.0 / 512.0)`
TARGET = 4.5

# Text colours and the surfaces they sit on, from tailwind.config.ts and index.css.
TEXT = {
    "ink": (0xF4, 0xF6, 0xFB),
    "ink-muted": (0xD3, 0xDA, 0xE9),
    "ink-faint": (0xAA, 0xB4, 0xCC),
}
SURFACES = {
    "glass panel": [((14, 16, 24), 0.62)],
    "chrome scrim": [((5, 6, 10), 0.72)],
}
REQUIREMENTS = [(text, surface) for surface in ("glass panel", "chrome scrim") for text in TEXT]

# Invariants this proof depends on. If the shader stops satisfying them, the bound is void.
SHADER_INVARIANTS = {
    "uMaxLuma": "the luminance ceiling",
    "accum / total": "the normalised weighted average that makes the blend convex",
}


def load_presets() -> dict[str, dict]:
    data = json.loads(PRESETS_JSON.read_text())
    return {key: value for key, value in data.items() if not key.startswith("_")}


def linear_luminance(colour: list[float] | tuple[float, ...]) -> float:
    return 0.2126 * colour[0] + 0.7152 * colour[1] + 0.0722 * colour[2]


def brightest_producible(preset: dict) -> tuple[float, str]:
    """The exact upper bound, and which colour sets it."""
    candidates = [("base", preset["base"])] + [
        (f"blob {i}", blob["color"]) for i, blob in enumerate(preset["blobs"])
    ]
    label, colour = max(candidates, key=lambda item: linear_luminance(item[1]))
    unclamped = linear_luminance(colour) * MAX_GAIN
    return min(preset["maxLuma"], unclamped) + DITHER, label


def to_srgb(linear: float) -> float:
    return 12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055


def to_linear(srgb: float) -> float:
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def composite_luminance(
    background: float, layers: list[tuple[tuple[int, int, int], float]]
) -> float:
    """CSS composites in sRGB space, so convert, blend, and convert back.

    The background is treated as a neutral of the given luminance: a coloured background of equal
    luminance composites to the same luminance under an opaque-ish neutral overlay.
    """
    current = [to_srgb(background)] * 3
    for rgb, alpha in layers:
        over = [channel / 255 for channel in rgb]
        current = [o * alpha + c * (1 - alpha) for o, c in zip(over, current, strict=True)]
    return linear_luminance([to_linear(channel) for channel in current])


def text_luminance(rgb: tuple[int, int, int]) -> float:
    return linear_luminance([to_linear(channel / 255) for channel in rgb])


def contrast(text_rgb: tuple[int, int, int], surface_luminance: float) -> float:
    lighter = max(text_luminance(text_rgb), surface_luminance)
    darker = min(text_luminance(text_rgb), surface_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    source = FRAG.read_text()
    missing = [name for name in SHADER_INVARIANTS if name not in source]
    if missing:
        for name in missing:
            print(
                f"mesh.frag no longer contains {name!r} ({SHADER_INVARIANTS[name]}); "
                "this proof no longer holds",
                file=sys.stderr,
            )
        return 1

    failures: list[str] = []
    for preset_name, preset in sorted(load_presets().items()):
        ceiling, source_label = brightest_producible(preset)
        clamped = (
            linear_luminance(
                max([preset["base"]] + [b["color"] for b in preset["blobs"]], key=linear_luminance)
            )
            * MAX_GAIN
            > preset["maxLuma"]
        )
        note = " (ceiling binds)" if clamped else ""
        print(
            f"{preset_name}: brightest producible luminance {ceiling:.3f} from {source_label}{note}"
        )
        for text_name, surface_name in REQUIREMENTS:
            surface = composite_luminance(ceiling, SURFACES[surface_name])
            ratio = contrast(TEXT[text_name], surface)
            print(
                f"  {'ok ' if ratio >= TARGET else 'FAIL'} {text_name:>10} on "
                f"{surface_name:<13} {ratio:5.2f}:1"
            )
            if ratio < TARGET:
                failures.append(f"{preset_name}: {text_name} on {surface_name} is {ratio:.2f}:1")

    if failures:
        print("\ncontrast failures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"\nall body text clears {TARGET}:1 against the brightest frame the shader can produce")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
