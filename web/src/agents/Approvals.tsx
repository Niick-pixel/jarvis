// The gate, as a screen. It sits above the composer wherever you are, because a job is parked
// waiting for this answer and hiding it inside a panel would mean the run just stalls.
//
// The target is shown verbatim and never truncated: it is the thing you are approving.
import { AnimatePresence, motion } from "framer-motion";
import { useAgents } from "../store/agents";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

export default function Approvals() {
  const pending = useAgents((s) => s.pending);
  const busy = useAgents((s) => s.busy);
  const decide = useAgents((s) => s.decide);

  return (
    <AnimatePresence>
      {pending.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={SPRING}
          className="mx-auto w-full max-w-4xl px-6 pb-2"
        >
          {pending.map((call) => (
            <div
              key={call.id}
              className="glass mb-2 rounded-2xl border-amber-300/25 bg-amber-300/5 p-3"
            >
              <div className="flex flex-wrap items-baseline gap-2 text-sm">
                <span className="font-medium text-ink">{call.tool}</span>
                <span className="text-ink-muted">
                  wants to run{call.job_name ? ` for “${call.job_name}”` : ""}
                </span>
              </div>
              <div className="mt-1 break-all font-mono text-xs text-ink">{call.target}</div>
              <div className="mt-1 break-all font-mono text-xs text-ink-faint">
                {call.args_preview}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  disabled={busy === call.id}
                  onClick={() => void decide(call.id, true, false)}
                >
                  Approve once
                </Button>
                <Button
                  disabled={busy === call.id}
                  onClick={() => void decide(call.id, true, true)}
                  title="Approve, and stop asking for this tool in this directory or on this host"
                >
                  Always allow here
                </Button>
                <Button disabled={busy === call.id} onClick={() => void decide(call.id, false, false)}>
                  Deny
                </Button>
              </div>
            </div>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
