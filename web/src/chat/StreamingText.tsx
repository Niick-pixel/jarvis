// Per-word fade-in. Section 5.4 is right that per-character is nauseating at 100 tok/s; words
// that are already on screen keep their identity through the key, so they never re-animate.
import { motion, useReducedMotion } from "framer-motion";
import { useMemo } from "react";
import { SOFT_SPRING } from "../ui/motion";

export default function StreamingText({ text }: { text: string }) {
  const reduced = useReducedMotion();
  const words = useMemo(() => text.split(/(\s+)/), [text]);

  if (reduced) return <span className="whitespace-pre-wrap">{text}</span>;

  return (
    <span className="whitespace-pre-wrap">
      {words.map((word, index) =>
        word.trim() === "" ? (
          <span key={`s${index}`}>{word}</span>
        ) : (
          <motion.span
            key={`w${index}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={SOFT_SPRING}
          >
            {word}
          </motion.span>
        ),
      )}
    </span>
  );
}
