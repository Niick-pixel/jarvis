// The top alternatives at one token. Picking one truncates the message there, forces your choice,
// and generation carries on — steering at the token level.
import { motion } from "framer-motion";
import type { TokenView } from "../api/types";
import { SPRING } from "../ui/motion";

const POPOVER_SURFACE = {
  background: "rgb(13, 15, 22)",
  boxShadow: "0 12px 32px rgba(0,0,0,0.55)",
} as const;

export default function TokenPopover({
  token,
  onPick,
  onClose,
}: {
  token: TokenView;
  onPick: (alternative: string) => void;
  onClose: () => void;
}) {
  if (token.top.length === 0) {
    return (
      <motion.span
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={SPRING}
        style={POPOVER_SURFACE}
        className="absolute left-0 top-full z-40 mt-1 w-64 rounded-xl border border-white/15 p-2 text-[11px] text-ink-faint"
      >
        This backend reported no alternatives for this token.
        <button onClick={onClose} className="ml-2 underline">
          close
        </button>
      </motion.span>
    );
  }

  return (
    <motion.span
      initial={{ opacity: 0, y: 4, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={SPRING}
      style={POPOVER_SURFACE}
      className="absolute left-0 top-full z-40 mt-1 block w-72 rounded-xl border border-white/15 p-2"
    >
      <span className="mb-1 flex items-center justify-between px-1 text-[10px] uppercase tracking-wide text-ink-faint">
        <span>alternatives at token {token.idx}</span>
        <button onClick={onClose} className="hover:text-ink">
          ✕
        </button>
      </span>
      {token.top.map((alternative, index) => {
        const p = Math.exp(alternative.logprob);
        const chosen = index === 0;
        return (
          <button
            key={`${alternative.token}-${index}`}
            onClick={() => onPick(alternative.token)}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-white/10"
            title={chosen ? "What the model actually picked" : "Force this instead and continue"}
          >
            <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink">
              {alternative.token === "" ? "∅" : alternative.token}
            </span>
            <span className="h-1 w-16 overflow-hidden rounded-full bg-white/10">
              <span
                className="block h-full rounded-full bg-sky-300/70"
                style={{ width: `${Math.max(2, p * 100)}%` }}
              />
            </span>
            <span className="w-10 text-right font-mono text-[10px] text-ink-faint">
              {p.toFixed(2)}
            </span>
          </button>
        );
      })}
    </motion.span>
  );
}
