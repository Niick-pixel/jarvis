"""Verify body text clears 4.5:1 against the brightest frame the shader can actually produce.

Section 5.5 says to test the shader's real extremes rather than a screenshot. A screenshot only
proves one frame was fine. Instead this evaluates the shader's colour path directly: the noise
functions only ever choose the scalar `v` fed to `palette()`, so sweeping `v` across its whole
range - then applying the pulse gain, the error mix and the luminance ceiling exactly as the
fragment shader does - enumerates every colour the background can produce.

Run by `make check`. If it fails, the fix is to darken the preset or the scrim, not to relax it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS_TS = ROOT / "web" / "src" / "scene" / "presets.ts"
FRAG = ROOT / "web" / "src" / "scene" / "shaders" / "warp.frag"

PULSE_GAIN = 0.10  # `col *= 1.0 + 0.10 * uPulse`
TARGET = 4.5

# Text colours and the surface each is drawn on, from index.css / tailwind.config.ts.
TEXT = {
    "ink": (0xF4, 0xF6, 0xFB),
    "ink-muted": (0xD3, 0xDA, 0xE9),
    "ink-faint": (0xAA, 0xB4, 0xCC),
}
# (name, rgb, alpha) composited over the background, in order.
SURFACES = {
    "glass panel": [((14, 16, 24), 0.62)],
    "chrome scrim": [((5, 6, 10), 0.72)],
}
# Which text colour must clear 4.5:1 on which surface.
REQUIREMENTS = [
    ("ink", "glass panel"),
    ("ink-muted", "glass panel"),
    ("ink-faint", "glass panel"),
    ("ink", "chrome scrim"),
    ("ink-muted", "chrome scrim"),
    ("ink-faint", "chrome scrim"),
]


def parse_presets() -> dict[str, tuple[list[tuple[float, float, float]], float]]:
    text = PRESETS_TS.read_text()
    out: dict[str, tuple[list[tuple[float, float, float]], float]] = {}
    for block in re.finditer(
        r"(\w+):\s*\{\s*name:.*?stops:\s*\[(.*?)\],\s*maxLuma:\s*([\d.]+)", text, re.S
    ):
        name, raw_stops, max_luma = block.group(1), block.group(2), float(block.group(3))
        stops = [
            tuple(float(v) for v in row.split(","))  # type: ignore[misc]
            for row in re.findall(r"\[([^\]]+)\]", raw_stops)
        ]
        out[name] = (stops, max_luma)  # type: ignore[assignment]
    return out


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def mix(a: tuple[float, ...], b: tuple[float, ...], t: float) -> tuple[float, ...]:
    return tuple(x + (y - x) * t for x, y in zip(a, b, strict=True))


def palette(stops: list[tuple[float, float, float]], v: float) -> tuple[float, ...]:
    """A direct transcription of palette() in warp.frag."""
    t = min(1.0, max(0.0, v * 0.5 + 0.5))
    c = mix(stops[0], stops[1], smoothstep(0.00, 0.30, t))
    c = mix(c, stops[2], smoothstep(0.25, 0.55, t))
    c = mix(c, stops[3], smoothstep(0.50, 0.78, t))
    return mix(c, stops[4], smoothstep(0.74, 1.00, t))


def linear_luminance(c: tuple[float, ...]) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def brightest_linear(stops: list[tuple[float, float, float]], max_luma: float) -> tuple[float, ...]:
    """Every colour the shader can emit, at its brightest, after the ceiling is applied."""
    best: tuple[float, ...] = (0.0, 0.0, 0.0)
    best_luma = -1.0
    for step in range(0, 2001):
        v = -1.0 + step / 1000.0
        colour = tuple(min(1.0, ch * (1.0 + PULSE_GAIN)) for ch in palette(stops, v))
        luma = linear_luminance(colour)
        if luma > max_luma:
            colour = tuple(ch * max_luma / luma for ch in colour)
            luma = max_luma
        if luma > best_luma:
            best, best_luma = colour, luma
    return best


def to_srgb(linear: float) -> float:
    return 12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055


def to_linear(srgb: float) -> float:
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def composite(
    background_linear: tuple[float, ...], layers: list[tuple[tuple[int, int, int], float]]
) -> tuple[float, ...]:
    """CSS composites in sRGB space, so convert, blend, and convert back."""
    current = [to_srgb(ch) for ch in background_linear]
    for rgb, alpha in layers:
        over = [ch / 255 for ch in rgb]
        current = [o * alpha + c * (1 - alpha) for o, c in zip(over, current, strict=True)]
    return tuple(to_linear(ch) for ch in current)


def relative_luminance_srgb(rgb: tuple[int, int, int]) -> float:
    r, g, b = (to_linear(ch / 255) for ch in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(text_rgb: tuple[int, int, int], surface_linear: tuple[float, ...]) -> float:
    l1 = relative_luminance_srgb(text_rgb)
    l2 = linear_luminance(surface_linear)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    presets = parse_presets()
    if not presets:
        print("could not parse presets.ts", file=sys.stderr)
        return 1
    if "uMaxLuma" not in FRAG.read_text():
        print("warp.frag no longer clamps luminance; this check assumes it does", file=sys.stderr)
        return 1

    failures: list[str] = []
    for preset, (stops, max_luma) in sorted(presets.items()):
        brightest = brightest_linear(stops, max_luma)
        print(f"{preset}: brightest producible luminance {linear_luminance(brightest):.3f}")
        for text_name, surface_name in REQUIREMENTS:
            surface = composite(brightest, SURFACES[surface_name])
            ratio = contrast(TEXT[text_name], surface)
            status = "ok " if ratio >= TARGET else "FAIL"
            print(f"  {status} {text_name:>10} on {surface_name:<13} {ratio:5.2f}:1")
            if ratio < TARGET:
                failures.append(f"{preset}: {text_name} on {surface_name} is {ratio:.2f}:1")

    if failures:
        print("\ncontrast failures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"\nall body text clears {TARGET}:1 against the brightest frame the shader can produce")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
