// The Memory page (BRIEF.md 4.7): everything the app remembers about you, as editable files.
// Each row shows where it came from, how often it has actually been used, and offers a hard delete.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { MemoryCommit, MemoryEntry } from "../api/types";
import { useMemory } from "../store/memory";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

function used(entry: MemoryEntry): string {
  if (!entry.retrieved_count) return "never used yet";
  const days = entry.last_used_at
    ? Math.floor((Date.now() - entry.last_used_at) / 86_400_000)
    : null;
  const when = days === null ? "" : days === 0 ? ", last used today" : `, last used ${days}d ago`;
  return `retrieved ${entry.retrieved_count}×${when}`;
}

function Row({ entry }: { entry: MemoryEntry }) {
  const { edit, forget } = useMemory();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.content);
  const [history, setHistory] = useState<MemoryCommit[] | null>(null);

  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-ink-faint">
        <span className={entry.source === "auto" ? "text-sky-300/80" : ""}>{entry.source}</span>
        <span>· {entry.scope}</span>
        {entry.always && <span className="text-violet-300/80">· always</span>}
        <span className="normal-case">· {used(entry)}</span>
        <span className="ml-auto flex gap-1">
          <button
            onClick={() => void edit(entry.id, { always: !entry.always })}
            className="rounded px-1.5 py-0.5 normal-case hover:bg-white/10 hover:text-ink"
            title="Always inject this, regardless of relevance"
          >
            {entry.always ? "unpin" : "always"}
          </button>
          <button
            onClick={() => setEditing(!editing)}
            className="rounded px-1.5 py-0.5 normal-case hover:bg-white/10 hover:text-ink"
          >
            edit
          </button>
          <button
            onClick={() => void api.memoryHistory(entry.id).then(setHistory)}
            className="rounded px-1.5 py-0.5 normal-case hover:bg-white/10 hover:text-ink"
          >
            history
          </button>
          <button
            onClick={() => void forget(entry.id)}
            className="rounded px-1.5 py-0.5 normal-case hover:bg-white/10 hover:text-rose-200"
            title="Delete the file. Not a tombstone, not a soft flag."
          >
            forget
          </button>
        </span>
      </div>

      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={3}
            className="w-full resize-y rounded-lg border border-white/15 bg-black/30 p-2 text-[13px] text-ink outline-none"
          />
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={() => {
                void edit(entry.id, { content: draft });
                setEditing(false);
              }}
            >
              Save
            </Button>
            <Button onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <p className="text-[13px] text-ink">{entry.content}</p>
      )}

      <p className="mt-1 font-mono text-[10px] text-ink-faint">memory/{entry.path}</p>
      {history && (
        <ul className="mt-2 space-y-0.5 border-t border-white/8 pt-2 font-mono text-[10px] text-ink-faint">
          {history.length === 0 && <li>no git history for this file yet</li>}
          {history.map((commit) => (
            <li key={commit.sha}>
              {commit.sha} · {commit.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function MemoryPage({ onClose }: { onClose: () => void }) {
  const { entries, refresh, add, loading } = useMemory();
  const [draft, setDraft] = useState("");

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  return (
    <motion.aside
      initial={{ x: 24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 24, opacity: 0 }}
      transition={SPRING}
      className="scrim flex h-full w-[26rem] shrink-0 flex-col border-l border-white/8"
    >
      <div className="flex items-center gap-2 px-3 py-3">
        <span className="text-xs uppercase tracking-wide text-ink-faint">
          Memory · {entries.length}
        </span>
        <Button onClick={onClose} title="Hide">
          ✕
        </Button>
      </div>

      <div className="px-3 pb-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && draft.trim()) {
              void add(draft.trim().slice(0, 56), draft.trim(), false);
              setDraft("");
            }
          }}
          placeholder="Remember something…"
          className="w-full rounded-xl border border-white/12 bg-black/25 px-3 py-1.5 text-[13px] text-ink outline-none placeholder:text-ink-faint"
        />
      </div>

      <div className="scroll-thin flex-1 space-y-2 overflow-y-auto px-3 pb-4">
        {loading && entries.length === 0 && (
          <p className="text-[11px] text-ink-faint">reading ./memory…</p>
        )}
        {!loading && entries.length === 0 && (
          <p className="text-[11px] text-ink-faint">
            Nothing remembered yet. Facts land here automatically after a conversation, and you can
            add, edit or delete any of them — they are Markdown files in ./memory.
          </p>
        )}
        <AnimatePresence>
          {entries.map((entry) => (
            <motion.div key={entry.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <Row entry={entry} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </motion.aside>
  );
}
