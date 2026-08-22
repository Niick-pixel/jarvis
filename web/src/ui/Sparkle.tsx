// The active-generation mark: a four-pointed sparkle that lights while the model is working.
// Deliberately a generic sparkle glyph rather than any vendor's logo.
import { motion, useReducedMotion } from "framer-motion";
import { useSession } from "../store/session";
import { SOFT_SPRING, SPRING } from "./motion";

const SPARKLE =
  "M12 1.6c.55 5.9 4.5 9.85 10.4 10.4-5.9.55-9.85 4.5-10.4 10.4-.55-5.9-4.5-9.85-10.4-10.4 5.9-.55 9.85-4.5 10.4-10.4z";

export default function Sparkle({ size = 18 }: { size?: number }) {
  const visual = useSession((s) => s.visual);
  const tokenTick = useSession((s) => s.tokenTick);
  const reduced = useReducedMotion();
  const active = visual === "thinking" || visual === "streaming" || visual === "listening";

  if (reduced) {
    return (
      <span
        aria-hidden
        className="inline-block rounded-full transition-opacity"
        style={{
          width: size * 0.45,
          height: size * 0.45,
          opacity: active ? 0.9 : 0.25,
          background: "rgb(167,190,255)",
        }}
      />
    );
  }

  return (
    <motion.svg
      aria-hidden
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className="shrink-0 overflow-visible"
      animate={{
        opacity: active ? 1 : 0.3,
        // A small kick on each arriving token, so the mark breathes with generation.
        scale: active ? [1, 1.12, 1] : 1,
        rotate: active ? 90 : 0,
      }}
      key={visual === "streaming" ? Math.floor(tokenTick / 6) : visual}
      transition={{ scale: SOFT_SPRING, rotate: { duration: 2.4, ease: "linear" }, opacity: SPRING }}
    >
      <defs>
        <linearGradient id="sparkle-fill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8ec5ff" />
          <stop offset="45%" stopColor="#b79dff" />
          <stop offset="100%" stopColor="#ffc46b" />
        </linearGradient>
      </defs>
      <path
        d={SPARKLE}
        fill="url(#sparkle-fill)"
        style={{ filter: active ? "drop-shadow(0 0 6px rgba(150,170,255,0.55))" : "none" }}
      />
    </motion.svg>
  );
}
