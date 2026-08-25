// RAG over your own disk (BRIEF.md 4.8): which folders are indexed, how far along, and which
// retrievers are actually running. Indexing is pausable and never competes with generation.
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { IndexProgress, RetrievalStatus, Source } from "../api/types";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

export default function SourcesPanel({ onClose }: { onClose: () => void }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [progress, setProgress] = useState<Record<string, IndexProgress>>({});
  const [status, setStatus] = useState<RetrievalStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const [list, stat] = await Promise.all([api.sources(), api.retrievalStatus()]);
    setSources(list);
    setStatus(stat);
  };

  useEffect(() => {
    void load().catch(() => undefined);
    const timer = window.setInterval(() => {
      void api
        .indexProgress()
        .then((rows) => setProgress(Object.fromEntries(rows.map((r) => [r.source_id, r]))))
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const add = async () => {
    if (!draft.trim()) return;
    setError("");
    try {
      await api.addSource(draft.trim());
      setDraft("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

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
          Knowledge · {sources.length}
        </span>
        <div className="ml-auto flex gap-1">
          <Button
            onClick={() => {
              const next = !paused;
              setPaused(next);
              void api.pauseIndexing(next).catch(() => undefined);
            }}
            variant={paused ? "primary" : "ghost"}
            title="Indexing yields to generation automatically; this pauses it entirely"
          >
            {paused ? "Paused" : "Pause"}
          </Button>
          <Button onClick={onClose}>✕</Button>
        </div>
      </div>

      {status && (
        <p className="px-3 pb-2 text-[11px] text-ink-faint">
          <span className={status.vector ? "text-emerald-300/80" : "text-amber-300/80"}>
            {status.vector ? "hybrid" : "keyword only"}
          </span>{" "}
          — {status.detail}
        </p>
      )}

      <div className="px-3 pb-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void add();
          }}
          placeholder="/home/you/notes — a folder to index"
          className="w-full rounded-xl border border-white/12 bg-black/25 px-3 py-1.5 font-mono text-[12px] text-ink outline-none placeholder:text-ink-faint"
        />
        {error && <p className="mt-1 text-[11px] text-rose-200">{error}</p>}
      </div>

      <div className="scroll-thin flex-1 space-y-2 overflow-y-auto px-3 pb-4">
        {sources.length === 0 && (
          <p className="text-[11px] text-ink-faint">
            No folders indexed. Add one above and its contents become searchable — every answer that
            uses a chunk cites the file and the exact byte range it came from.
          </p>
        )}
        {sources.map((source) => {
          const live = progress[source.id];
          const pct = live?.files_total
            ? Math.round((live.files_done / live.files_total) * 100)
            : 0;
          return (
            <div key={source.id} className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-ink-faint">
                <span>{source.kind}</span>
                <span
                  className={source.observer === "polling" ? "text-amber-300/80" : ""}
                  title={
                    source.observer === "polling"
                      ? "Windows drives do not deliver inotify events to WSL2, so this one is polled"
                      : "Watched natively with inotify"
                  }
                >
                  · {source.observer}
                </span>
                <span className="ml-auto flex gap-1">
                  <button
                    onClick={() => void api.indexSource(source.id).catch(() => undefined)}
                    className="rounded px-1.5 py-0.5 normal-case hover:bg-white/10 hover:text-ink"
                  >
                    index
                  </button>
                  <button
                    onClick={() => void api.removeSource(source.id).then(load)}
                    className="rounded px-1.5 py-0.5 normal-case hover:bg-white/10 hover:text-rose-200"
                  >
                    remove
                  </button>
                </span>
              </div>
              <p className="mt-1 truncate font-mono text-[12px] text-ink">{source.path}</p>
              <p className="mt-1 text-[11px] text-ink-faint">
                {source.file_count} files · {source.chunk_count} chunks
              </p>
              {live && live.state !== "done" && live.state !== "idle" && (
                <>
                  <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/8">
                    <motion.div
                      className="h-full rounded-full bg-sky-300/70"
                      animate={{ width: `${pct}%` }}
                      transition={SPRING}
                    />
                  </div>
                  <p className="mt-1 text-[10px] text-ink-faint">
                    {live.state} — {live.detail}
                  </p>
                </>
              )}
            </div>
          );
        })}
      </div>
    </motion.aside>
  );
}
