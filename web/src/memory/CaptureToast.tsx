// "Saved 2 things", with what they were and one click to undo.
//
// This is the whole difference between capture that is automatic and capture that is silent. You
// see every fact the moment it is written, and removing it is one click, not an archaeology dig.
import { AnimatePresence, motion } from "framer-motion";
import { useMemory } from "../store/memory";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

export default function CaptureToast() {
  const batch = useMemory((s) => s.lastCapture);
  const undo = useMemory((s) => s.undoCapture);
  const dismiss = useMemory((s) => s.dismissCapture);

  return (
    <AnimatePresence>
      {batch && batch.entries.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.97 }}
          transition={SPRING}
          className="glass pointer-events-auto fixed bottom-28 left-6 z-50 w-[30rem] rounded-2xl p-3"
        >
          <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-ink-faint">
            <span className="h-2 w-2 rounded-full bg-emerald-300/80" />
            saved {batch.entries.length} thing{batch.entries.length > 1 ? "s" : ""} to memory
            <div className="ml-auto flex gap-1">
              <Button onClick={() => void undo()} title="Delete exactly what this capture wrote">
                Undo
              </Button>
              <Button onClick={dismiss}>Keep</Button>
            </div>
          </div>
          <ul className="space-y-1">
            {batch.entries.map((entry) => (
              <li key={entry.id} className="truncate text-[12px] text-ink-muted">
                · {entry.content}
              </li>
            ))}
          </ul>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
