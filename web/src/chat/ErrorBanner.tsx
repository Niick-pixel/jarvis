// Errors arrive with a machine-readable remedy, so this renders a button that fixes the problem
// instead of a stack trace the user has to decode.
import { AnimatePresence, motion } from "framer-motion";
import { useSession } from "../store/session";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

export default function ErrorBanner() {
  const error = useSession((s) => s.error);
  const applyRemedy = useSession((s) => s.applyRemedy);
  const dismiss = useSession((s) => s.dismissError);

  return (
    <AnimatePresence>
      {error && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={SPRING}
          className="mx-auto mb-3 w-full max-w-4xl px-6"
        >
          <div className="flex items-start gap-3 rounded-2xl border border-rose-400/30 bg-rose-500/12 px-4 py-3">
            <div className="flex-1">
              <p className="text-sm text-rose-100">{error.message}</p>
              <p className="mt-0.5 font-mono text-[11px] text-rose-200/60">{error.code}</p>
            </div>
            {error.remedy && (
              <Button variant="primary" onClick={() => void applyRemedy(error.remedy!)}>
                {error.remedy.label}
              </Button>
            )}
            <Button onClick={dismiss}>Dismiss</Button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
