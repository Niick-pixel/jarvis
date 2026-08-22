// The strongest "the machine is thinking" signal in the app, and close to free: one blurred,
// masked, slowly rotating conic ring. Opacity springs with the state; nothing else moves.
import { motion, useReducedMotion } from "framer-motion";
import { useSession } from "../store/session";
import { SPRING } from "../ui/motion";

const OPACITY: Record<string, number> = {
  idle: 0,
  listening: 0.9,
  thinking: 0.9,
  streaming: 0.55,
  error: 0.7,
};

export default function EdgeGlow() {
  const visual = useSession((s) => s.visual);
  const reduced = useReducedMotion();
  const hue = visual === "error" ? "0, 90%, 60%" : "265, 90%, 66%";

  return (
    <motion.div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-20"
      initial={{ opacity: 0 }}
      animate={{ opacity: OPACITY[visual] ?? 0 }}
      transition={reduced ? { duration: 0 } : SPRING}
      style={{
        // Masked to the viewport border so the middle of the screen stays untouched.
        WebkitMaskImage:
          "linear-gradient(#000,#000), linear-gradient(#000,#000)",
        maskImage: "linear-gradient(#000,#000), linear-gradient(#000,#000)",
        WebkitMaskClip: "padding-box, border-box",
        WebkitMaskComposite: "xor",
        maskComposite: "exclude",
        border: "70px solid transparent",
        filter: "blur(48px)",
      }}
    >
      <motion.div
        className="h-full w-full"
        style={{
          background: `conic-gradient(from 0deg, hsl(${hue} / 0.0), hsl(${hue} / 0.85), hsl(190 90% 60% / 0.7), hsl(${hue} / 0.0))`,
        }}
        animate={reduced ? undefined : { rotate: 360 }}
        transition={{ duration: 26, repeat: Infinity, ease: "linear" }}
      />
    </motion.div>
  );
}
