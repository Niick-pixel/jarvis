// Presentation settings. Persisted locally so the app opens the way you left it; nothing here
// ever leaves the machine.
import { create } from "zustand";
import type { PresetName } from "../scene/presets";

const KEY = "jarvis.visual";

interface Stored {
  preset: PresetName;
  performanceMode: boolean;
}

function load(): Stored {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { preset: "aurora", performanceMode: false, ...JSON.parse(raw) };
  } catch {
    // A blocked or corrupt localStorage must never stop the app from starting.
  }
  return { preset: "aurora", performanceMode: false };
}

interface VisualState extends Stored {
  setPreset: (preset: PresetName) => void;
  setPerformanceMode: (value: boolean) => void;
}

export const useVisual = create<VisualState>((set, get) => ({
  ...load(),
  setPreset: (preset) => {
    set({ preset });
    persist(get());
  },
  setPerformanceMode: (performanceMode) => {
    set({ performanceMode });
    persist(get());
  },
}));

function persist(state: Stored): void {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ preset: state.preset, performanceMode: state.performanceMode }),
    );
  } catch {
    // Nothing here is worth failing a render over.
  }
}
