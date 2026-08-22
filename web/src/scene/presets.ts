// Three palettes, each stored as five stops the shader blends with smoothstep.
export interface Preset {
  name: string;
  stops: [number, number, number][];
  /** Luminance ceiling. Enforced in the shader so the contrast check has something to verify. */
  maxLuma: number;
}

export const PRESETS: Record<"aurora" | "solar" | "deep", Preset> = {
  aurora: {
    name: "Aurora",
    stops: [
      [0.02, 0.05, 0.09],
      [0.03, 0.24, 0.29],
      [0.10, 0.16, 0.42],
      [0.36, 0.11, 0.45],
      [0.55, 0.13, 0.38],
    ],
    maxLuma: 0.30,
  },
  solar: {
    name: "Solar",
    stops: [
      [0.05, 0.03, 0.03],
      [0.31, 0.14, 0.05],
      [0.46, 0.20, 0.10],
      [0.51, 0.17, 0.22],
      [0.44, 0.12, 0.28],
    ],
    maxLuma: 0.30,
  },
  deep: {
    name: "Deep",
    stops: [
      [0.01, 0.01, 0.02],
      [0.03, 0.04, 0.08],
      [0.06, 0.09, 0.14],
      [0.10, 0.08, 0.19],
      [0.14, 0.13, 0.22],
    ],
    maxLuma: 0.22,
  },
};

export type PresetName = keyof typeof PRESETS;
