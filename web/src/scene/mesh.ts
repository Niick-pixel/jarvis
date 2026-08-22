// Where the colour centres are at a given moment.
//
// The motion lives here rather than in GLSL on purpose: six blobs is nothing to compute per
// frame, and having the paths in TypeScript means they are readable, adjustable, and shared with
// the CSS fallback so both renderings drift the same way. The shader is left doing one job -
// blending - which is the part that genuinely needs to run per pixel.
import type { Blob, Preset } from "./presets";

export interface BlobFrame {
  x: number;
  y: number;
  falloff: number;
  weight: number;
}

/** Lissajous wander. Energy speeds the drift up; it never makes it jump. */
export function blobAt(blob: Blob, time: number, energy: number, pulse: number): BlobFrame {
  const rate = blob.speed * (0.55 + 1.5 * energy);
  const t = time * rate + blob.phase;
  const swell = 1 + 0.22 * energy + 0.16 * pulse;
  return {
    x: blob.at[0] + blob.drift * swell * Math.sin(t),
    y: blob.at[1] + blob.drift * swell * Math.cos(t * 0.83 + blob.phase * 0.6),
    // Breathing shape: blobs widen and narrow slowly, which is what stops the field reading
    // as six circles sliding around behind frosted glass.
    falloff: blob.falloff * (1 - 0.20 * Math.sin(t * 1.31) - 0.12 * pulse),
    weight: blob.weight * (1 + 0.25 * pulse),
  };
}

export function blobFrames(
  preset: Preset,
  time: number,
  energy: number,
  pulse: number,
): BlobFrame[] {
  return preset.blobs.map((blob) => blobAt(blob, time, energy, pulse));
}

/** Linear-sRGB triple to a CSS rgb() string, for the non-shader fallback. */
export function toCss(color: [number, number, number], gain = 1): string {
  const channel = (value: number) => {
    const linear = Math.min(1, Math.max(0, value * gain));
    const srgb = linear <= 0.0031308 ? 12.92 * linear : 1.055 * linear ** (1 / 2.4) - 0.055;
    return Math.round(srgb * 255);
  };
  return `rgb(${channel(color[0])}, ${channel(color[1])}, ${channel(color[2])})`;
}
