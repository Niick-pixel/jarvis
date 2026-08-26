// One line above the composer for anything voice needs to say. Errors here are sentences, not
// codes, and they carry the command that changes the answer.
import { AnimatePresence, motion } from "framer-motion";
import { SPRING } from "../ui/motion";
import { useVoice } from "../store/voice";

export default function VoiceNotice() {
  const error = useVoice((s) => s.error);
  const dismiss = useVoice((s) => s.dismiss);
  const [message, fix] = split(error ?? "");

  return (
    <AnimatePresence>
      {error && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 6 }}
          transition={SPRING}
          className="mx-auto flex w-full max-w-4xl items-start gap-3 px-6 pb-2 text-sm text-ink-muted"
        >
          <span className="min-w-0 flex-1">
            {message}
            {fix && (
              <code className="ml-2 rounded bg-white/10 px-1.5 py-0.5 text-ink">{fix}</code>
            )}
          </span>
          <button onClick={dismiss} className="rounded-lg px-2 py-0.5 hover:bg-white/10">
            dismiss
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** The backend appends "Fix: <command>"; showing it as code makes it obviously copyable. */
function split(text: string): [string, string] {
  const marker = text.lastIndexOf("Fix: ");
  if (marker < 0) return [text, ""];
  return [text.slice(0, marker).trim(), text.slice(marker + 5).trim()];
}
