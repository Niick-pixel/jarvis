// One 0..1 signal that drives the orb, written by whoever is currently the source of energy:
// the microphone while you speak, the token stream while the model does, the speaker while it
// talks back. Kept out of React state on purpose - this is read every frame, and a setState per
// frame costs more than the drawing does (section 5.6).

const DECAY_PER_S = 2.4;
const RISE = 22;
const FALL = 9;

export class DriveSignal {
  /** Smoothed output, what the orb actually draws. */
  value = 0;
  private target = 0;
  private pulse = 0;

  /** Continuous sources (mic RMS, playback RMS) set the target directly. */
  set(level: number): void {
    this.target = Math.max(0, Math.min(1, level));
  }

  /** Discrete sources (one arriving token) add a decaying bump instead. */
  hit(amount = 0.35): void {
    this.pulse = Math.min(1, this.pulse + amount);
  }

  /** Advance by `dt` seconds. Rises fast and falls slowly, so speech reads as a shape. */
  step(dt: number): number {
    const clamped = Math.min(dt, 1 / 20);
    this.pulse = Math.max(0, this.pulse - DECAY_PER_S * clamped);
    const goal = Math.min(1, this.target + this.pulse);
    const rate = goal > this.value ? RISE : FALL;
    this.value += (goal - this.value) * Math.min(1, rate * clamped);
    return this.value;
  }

  reset(): void {
    this.value = 0;
    this.target = 0;
    this.pulse = 0;
  }
}

export const drive = new DriveSignal();

/** Root mean square of one analyser window, scaled so ordinary speech lands near 0.6. */
export function rms(samples: Float32Array): number {
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.min(1, Math.sqrt(sum / samples.length) * 6);
}
