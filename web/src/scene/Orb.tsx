// The orb (section 5.3): three metaballs merged by an SVG gooey filter, sized by whatever is
// currently driving the conversation - mic level while you talk, token arrival rate while the
// model does, playback level while it talks back.
//
// SVG rather than a second WebGL context: the background already owns the GPU, and section 5.6
// budgets 3% of it for decoration. A 26px filter costs a rounding error next to another canvas.
import { useEffect, useId, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import { useSession } from "../store/session";
import { useVoice } from "../store/voice";
import { drive } from "../voice/level";

const BLOBS = [
  { phase: 0, speed: 0.9, orbit: 0.2, size: 0.3 },
  { phase: 2.1, speed: -1.15, orbit: 0.26, size: 0.24 },
  { phase: 4.2, speed: 0.7, orbit: 0.16, size: 0.2 },
];
const HUES = {
  listening: "#8ec5ff",
  transcribing: "#b79dff",
  speaking: "#ffc46b",
  streaming: "#a7beff",
} as const;

export default function Orb({ size = 26 }: { size?: number }) {
  const reduced = useReducedMotion();
  const phase = useVoice((s) => s.phase);
  const visual = useSession((s) => s.visual);
  const circles = useRef<(SVGCircleElement | null)[]>([]);
  const filterId = useId();
  const active = phase !== "idle" || visual === "streaming";
  const colour = HUES[phase === "idle" ? "streaming" : phase];

  // Each token is a discrete event, so it becomes a bump on the same signal the mic writes to.
  useEffect(
    () =>
      useSession.subscribe((state, previous) => {
        if (state.tokenTick !== previous.tokenTick) drive.hit(0.3);
      }),
    [],
  );

  useEffect(() => {
    if (reduced || !active) return;
    let last = performance.now();
    let frame = requestAnimationFrame(function tick(now: number) {
      const dt = (now - last) / 1000;
      last = now;
      const level = drive.step(dt);
      const t = now / 1000;
      BLOBS.forEach((blob, index) => {
        const node = circles.current[index];
        if (!node) return;
        const angle = blob.phase + t * blob.speed;
        const orbit = size * blob.orbit * (0.35 + 0.65 * level);
        node.setAttribute("cx", String(size / 2 + Math.cos(angle) * orbit));
        node.setAttribute("cy", String(size / 2 + Math.sin(angle) * orbit));
        node.setAttribute("r", String(size * blob.size * (0.6 + 0.7 * level)));
      });
      frame = requestAnimationFrame(tick);
    });
    return () => {
      cancelAnimationFrame(frame);
      drive.reset();
    };
  }, [active, reduced, size]);

  if (reduced) {
    // Section 5.5: the orb becomes a simple pulse dot, and no frame loop runs at all.
    return (
      <span
        aria-hidden
        className="inline-block rounded-full"
        style={{
          width: size * 0.42,
          height: size * 0.42,
          background: colour,
          opacity: active ? 0.95 : 0.25,
        }}
      />
    );
  }

  return (
    <svg
      aria-hidden
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0 overflow-visible"
      style={{
        opacity: active ? 1 : 0.35,
        filter: active ? `drop-shadow(0 0 7px ${colour}66)` : "none",
        willChange: active ? "filter" : undefined,
      }}
    >
      <defs>
        <filter id={filterId}>
          {/* Blur, then push alpha through a steep ramp: overlapping blobs fuse, gaps stay gaps. */}
          <feGaussianBlur in="SourceGraphic" stdDeviation={size * 0.11} result="soft" />
          <feColorMatrix
            in="soft"
            values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -8"
          />
        </filter>
      </defs>
      <g filter={`url(#${filterId})`} fill={colour}>
        {BLOBS.map((blob, index) => (
          <circle
            key={blob.phase}
            ref={(node) => {
              circles.current[index] = node;
            }}
            cx={size / 2}
            cy={size / 2}
            r={size * blob.size * 0.6}
          />
        ))}
      </g>
    </svg>
  );
}
