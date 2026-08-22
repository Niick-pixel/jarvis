// Section 5.4: springs only. There are no duration-based easings in the chat surface, so these
// are the only transition constants the app is allowed to use.
import type { Transition, Variants } from "framer-motion";

export const SPRING: Transition = { type: "spring", stiffness: 420, damping: 32, mass: 0.9 };

export const SOFT_SPRING: Transition = { type: "spring", stiffness: 260, damping: 30, mass: 1 };

export const PRESS = { scale: 0.97 };

export const messageVariants: Variants = {
  hidden: { opacity: 0, y: 14, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1, transition: SPRING },
};

export const listVariants: Variants = {
  visible: { transition: { staggerChildren: 0.025 } },
};
