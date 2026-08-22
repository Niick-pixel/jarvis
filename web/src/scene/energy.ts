// The state machine that drives the background, and the spring that keeps it physical.
//
// Section 5.1 is explicit that energy moves through a spring and never steps. This is a plain
// integrator rather than a Framer Motion value because it is read inside the render loop, where
// a React state update per frame would cost more than the shader does.
import type { VisualState } from "../store/session";

export const ENERGY_TARGETS: Record<VisualState, number> = {
  idle: 0.12,
  listening: 0.45,
  thinking: 0.85,
  streaming: 0.85,
  error: 0.35,
};

const STIFFNESS = 42;
const DAMPING = 11;
const PULSE_DECAY = 3.6;

export class EnergySpring {
  value = ENERGY_TARGETS.idle;
  private velocity = 0;
  pulse = 0;
  error = 0;

  /** Advance by `dt` seconds toward the target for `state`. */
  step(dt: number, state: VisualState): void {
    const clamped = Math.min(dt, 1 / 20);
    const target = ENERGY_TARGETS[state];
    const accel = STIFFNESS * (target - this.value) - DAMPING * this.velocity;
    this.velocity += accel * clamped;
    this.value += this.velocity * clamped;

    this.pulse = Math.max(0, this.pulse - PULSE_DECAY * clamped);
    const errorTarget = state === "error" ? 1 : 0;
    // 400ms to desaturate, per section 5.1.
    this.error += (errorTarget - this.error) * Math.min(1, clamped / 0.4);
  }

  /** Called on each arriving token, so the background breathes in sync with generation. */
  tick(): void {
    this.pulse = Math.min(1, this.pulse + 0.55);
  }

  settle(state: VisualState): void {
    this.value = ENERGY_TARGETS[state];
    this.velocity = 0;
    this.pulse = 0;
  }
}
