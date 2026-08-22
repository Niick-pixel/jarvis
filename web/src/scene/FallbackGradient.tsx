// Performance mode, and the reduced-motion path: a CSS mesh gradient with no GPU cost worth
// measuring. Same palette, no shader, no animation.
import { PRESETS, type PresetName } from "./presets";

const rgb = (stop: [number, number, number]) =>
  `rgb(${stop.map((c) => Math.round(c * 255)).join(",")})`;

export default function FallbackGradient({ preset }: { preset: PresetName }) {
  const stops = PRESETS[preset].stops;
  const layers = [
    `radial-gradient(60% 55% at 18% 22%, ${rgb(stops[3]!)} 0%, transparent 62%)`,
    `radial-gradient(55% 60% at 82% 28%, ${rgb(stops[4]!)} 0%, transparent 60%)`,
    `radial-gradient(70% 65% at 50% 92%, ${rgb(stops[2]!)} 0%, transparent 66%)`,
    `linear-gradient(160deg, ${rgb(stops[0]!)} 0%, ${rgb(stops[1]!)} 100%)`,
  ].join(",");
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10"
      style={{ background: layers }}
    />
  );
}
