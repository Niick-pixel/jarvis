// Every conversation ever held on this machine. They are rows in SQLite, not browser storage:
// close the app, reboot, come back in a year - they are still there, and still yours.
import { motion } from "framer-motion";
import { useEffect } from "react";
import { useLibrary } from "../store/library";
import { useSession } from "../store/session";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

function when(ms: number): string {
  const days = Math.floor((Date.now() - ms) / 86_400_000);
  if (days === 0) return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(ms).toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function Conversations({ onClose }: { onClose: () => void }) {
  const { conversations, refresh, open, create, remove } = useLibrary();
  const activeId = useSession((s) => s.conversation?.id);
  const running = useSession((s) => s.runId) !== null;

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -20, opacity: 0 }}
      transition={SPRING}
      className="scrim flex h-full w-72 shrink-0 flex-col border-r border-white/8"
    >
      <div className="flex items-center gap-2 px-3 py-3">
        <span className="text-xs uppercase tracking-wide text-ink-faint">Saved locally</span>
        <div className="ml-auto flex gap-1">
          <Button onClick={() => void create()} title="New conversation">
            New
          </Button>
          <Button onClick={onClose} title="Hide the list">
            ✕
          </Button>
        </div>
      </div>

      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-3">
        {conversations.length === 0 && (
          <p className="px-2 py-3 text-[11px] text-ink-faint">Nothing saved yet.</p>
        )}
        {conversations.map((conversation) => (
          <div
            key={conversation.id}
            className={`group mb-1 flex items-center gap-1 rounded-xl border px-2 py-2 ${
              conversation.id === activeId
                ? "border-white/20 bg-white/10"
                : "border-transparent hover:bg-white/6"
            }`}
          >
            <button
              onClick={() => void open(conversation.id)}
              disabled={running}
              className="min-w-0 flex-1 text-left disabled:opacity-50"
              title={running ? "Finish or stop the current generation first" : undefined}
            >
              <span className="block truncate text-sm text-ink">
                {conversation.title || "Untitled"}
              </span>
              <span className="text-[10px] text-ink-faint">{when(conversation.updated_at)}</span>
            </button>
            <button
              onClick={() => void remove(conversation.id)}
              className="rounded-lg px-1.5 py-1 text-[11px] text-ink-faint opacity-0 transition-opacity hover:bg-white/10 hover:text-rose-200 group-hover:opacity-100"
              title="Delete permanently - this is a hard delete, not an archive"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </motion.aside>
  );
}
