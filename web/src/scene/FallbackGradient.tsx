// Performance mode, and the reduced-motion path: the same six colour centres rendered as CSS
// radial gradients. Same palette and same resting layout as the shader, so switching modes
// changes the cost, not the design.
import { toCss } from "./mesh";
import { PRESETS, type PresetName } from "./presets";

export default function FallbackGradient({ preset }: { preset: PresetName }) {
  const config = PRESETS[preset];
  const layers = config.blobs
    .map((blob) => {
      const radius = Math.round(70 / Math.sqrt(blob.falloff));
      const x = Math.round(blob.at[0] * 100);
      const y = Math.round((1 - blob.at[1]) * 100);
      return `radial-gradient(${radius * 1.4}% ${radius}% at ${x}% ${y}%, ${toCss(blob.color)} 0%, transparent 68%)`;
    })
    .join(",");

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10"
      style={{ background: `${layers}, ${toCss(config.base)}` }}
    />
  );
}
