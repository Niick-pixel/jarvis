import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { PRESS, SPRING } from "./motion";

interface Props {
  onClick?: () => void;
  children: ReactNode;
  variant?: "primary" | "ghost";
  disabled?: boolean;
  title?: string;
  type?: "button" | "submit";
}

const STYLES = {
  primary: "bg-white/12 hover:bg-white/20 text-ink border-white/15",
  ghost: "bg-transparent hover:bg-white/8 text-ink-muted hover:text-ink border-transparent",
} as const;

export default function Button({
  onClick,
  children,
  variant = "ghost",
  disabled,
  title,
  type = "button",
}: Props) {
  const reduced = useReducedMotion();
  return (
    <motion.button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      whileTap={reduced || disabled ? undefined : PRESS}
      transition={SPRING}
      className={`rounded-xl border px-3 py-1.5 text-sm transition-colors disabled:opacity-40 ${STYLES[variant]}`}
    >
      {children}
    </motion.button>
  );
}
