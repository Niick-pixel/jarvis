// M1 shows what is in context and whether anything fell out of it. M2 turns this into the
// interactive stacked bar with per-block toggling, pinning and reordering.
import { AnimatePresence, motion } from "framer-motion";
import { useSession } from "../store/session";
import { SPRING } from "../ui/motion";

export default function ContextReadout() {
  const assembly = useSession((s) => s.assembly);
  if (!assembly) return null;

  const budget = assembly.ctx_len - assembly.max_gen_tokens;
  const used = Math.min(1, assembly.total_tokens / Math.max(budget, 1));
  const evicted = assembly.evictions ?? [];

  return (
    <div className="mx-auto w-full max-w-4xl px-6 pb-2 text-[11px] text-ink-faint">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/8">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-teal-300/70 to-violet-400/70"
          animate={{ width: `${used * 100}%` }}
          transition={SPRING}
        />
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3">
        <span>
          {assembly.total_tokens.toLocaleString()} / {budget.toLocaleString()} tokens in context
          {assembly.estimated && " (estimated - this backend has no tokenizer)"}
        </span>
        <span>·</span>
        <span>{assembly.blocks.filter((b) => b.included).length} blocks</span>
      </div>
      <AnimatePresence>
        {evicted.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={SPRING}
            className="mt-2 rounded-lg border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-amber-200/90"
          >
            {evicted.length} block{evicted.length > 1 ? "s" : ""} did not fit and{" "}
            {evicted.length > 1 ? "were" : "was"} dropped from this request:{" "}
            {evicted.map((e) => e.label).join(" · ")}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
