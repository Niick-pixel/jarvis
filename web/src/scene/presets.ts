// Palettes for the fluid mesh gradient. The data lives in presets.json because
// scripts/contrast_check.py reads the same file: one source, so the accessibility check can never
// validate a palette that differs from the one on screen.
import data from "./presets.json";

export interface Blob {
  color: [number, number, number];
  at: [number, number];
  drift: number;
  speed: number;
  phase: number;
  falloff: number;
  weight: number;
}

export interface Preset {
  name: string;
  maxLuma: number;
  base: [number, number, number];
  baseWeight: number;
  blobs: Blob[];
}

const { _comment, ...palettes } = data;

export const PRESETS = palettes as unknown as Record<"aurora" | "solar" | "deep", Preset>;
export type PresetName = keyof typeof PRESETS;

/** Every preset carries the same blob count, so the shader can use a constant loop bound. */
export const BLOB_COUNT = PRESETS.aurora.blobs.length;
