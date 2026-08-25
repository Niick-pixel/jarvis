// The Context Inspector (BRIEF.md 4.2): one segment per block, sized by tokens, coloured by kind.
// Click a segment to read exactly what went in; pin it so the budget can never evict it; switch it
// off entirely. Nothing leaves the context quietly - every drop is named below the bar.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ContextBlock, OpenedChunk } from "../api/types";
import { useContextInspector } from "../store/context";
import { useSession } from "../store/session";
import { SPRING } from "../ui/motion";

const KIND_COLOR: Record<string, string> = {
  system: "#7f8aa3",
  history: "#8ec5ff",
  memory: "#9be7c4",
  rag: "#ffc46b",
  web: "#7fe3c0",
  tool: "#e59bff",
  pinned: "#b79dff",
  nudge: "#ff9bb0",
};

function BlockDetail({ block, onClose }: { block: ContextBlock; onClose: () => void }) {
  const { toggle, pin } = useContextInspector();
  const [opened, setOpened] = useState<OpenedChunk | null>(null);
  const citable = block.kind === "rag" && block.source_ref?.includes("#");
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={SPRING}
      className="glass mb-2 rounded-2xl p-3"
    >
      <div className="mb-2 flex items-center gap-2 text-[11px] text-ink-faint">
        <span
          className="h-2 w-2 rounded-full"
          style={{ background: KIND_COLOR[block.kind] ?? "#8892a6" }}
        />
        <span className="uppercase tracking-wide">{block.kind}</span>
        <span>· {block.token_count} tokens</span>
        {block.eviction && <span className="text-amber-300/80">· {block.eviction}</span>}
        <div className="ml-auto flex gap-1">
          {citable && (
            <button
              onClick={() => void api.openCitation(block.source_ref!).then(setOpened)}
              className="rounded-lg px-2 py-0.5 hover:bg-white/10 hover:text-ink"
              title="Open the source file at the exact bytes this chunk came from"
            >
              open source
            </button>
          )}
          {block.source_ref && (
            <>
              <button
                onClick={() => void pin(block.source_ref!, !block.pinned)}
                className="rounded-lg px-2 py-0.5 hover:bg-white/10 hover:text-ink"
                title="Pinned blocks are never evicted to fit the budget"
              >
                {block.pinned ? "unpin" : "pin"}
              </button>
              <button
                onClick={() => void toggle(block.source_ref!, block.included)}
                className="rounded-lg px-2 py-0.5 hover:bg-white/10 hover:text-ink"
              >
                {block.included ? "exclude" : "include"}
              </button>
            </>
          )}
          <button onClick={onClose} className="rounded-lg px-2 py-0.5 hover:bg-white/10">
            close
          </button>
        </div>
      </div>
      {block.kind === "web" && block.source_ref && (
        <p className="mb-2 truncate font-mono text-[10px] text-emerald-200/80" title={block.source_ref}>
          {block.source_ref} — treated as data, never as instructions
        </p>
      )}
      {opened ? (
        <div>
          <p className="mb-1 font-mono text-[10px] text-sky-200/80">
            {opened.path}:{opened.line_number} · bytes {opened.byte_start}–{opened.byte_end}
          </p>
          <pre className="scroll-thin max-h-56 overflow-auto whitespace-pre-wrap text-[12px]">
            <span className="text-ink-faint">{opened.before}</span>
            <mark className="bg-sky-300/20 text-ink">{opened.text}</mark>
            <span className="text-ink-faint">{opened.after}</span>
          </pre>
          <button
            onClick={() => setOpened(null)}
            className="mt-1 text-[10px] text-ink-faint underline hover:text-ink"
          >
            back to the chunk as sent
          </button>
        </div>
      ) : (
        <pre className="scroll-thin max-h-48 overflow-auto whitespace-pre-wrap text-[12px] text-ink-muted">
          {block.content}
        </pre>
      )}
    </motion.div>
  );
}

export default function ContextBar() {
  const live = useSession((s) => s.assembly);
  const conversationId = useSession((s) => s.conversation?.id);
  const messages = useSession((s) => s.messages);
  const { preview, refresh } = useContextInspector();
  const [openId, setOpenId] = useState<string | null>(null);

  // The live assembly from the last run wins; otherwise show what the next request would carry.
  const assembly = live ?? preview;

  useEffect(() => {
    if (conversationId) void refresh().catch(() => undefined);
  }, [conversationId, messages.length, refresh]);

  if (!assembly) return null;

  const budget = assembly.ctx_len - assembly.max_gen_tokens;
  const included = assembly.blocks.filter((b) => b.included);
  const open = assembly.blocks.find((b) => b.id === openId);

  return (
    <div className="mx-auto w-full max-w-4xl px-6 pb-2">
      <AnimatePresence>
        {open && <BlockDetail key={open.id} block={open} onClose={() => setOpenId(null)} />}
      </AnimatePresence>

      <div className="flex h-2 w-full gap-[2px] overflow-hidden rounded-full bg-white/8">
        {included.map((block) => (
          <motion.button
            key={block.id}
            layout
            transition={SPRING}
            onClick={() => setOpenId(openId === block.id ? null : block.id)}
            style={{
              width: `${(block.token_count / Math.max(budget, 1)) * 100}%`,
              background: KIND_COLOR[block.kind] ?? "#8892a6",
              opacity: block.pinned ? 1 : 0.75,
            }}
            className="h-full min-w-[3px] rounded-full transition-opacity hover:opacity-100"
            title={`${block.label} — ${block.token_count} tokens${block.pinned ? " (pinned)" : ""}`}
          />
        ))}
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 text-[11px] text-ink-faint">
        <span>
          {assembly.total_tokens.toLocaleString()} / {budget.toLocaleString()} tokens
          {assembly.estimated && " (estimated — this backend has no tokenizer)"}
        </span>
        <span>· {included.length} blocks</span>
        {!live && <span>· preview of the next request</span>}
      </div>

      <AnimatePresence>
        {assembly.evictions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={SPRING}
            className="mt-2 rounded-lg border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-[11px] text-amber-200/90"
          >
            {assembly.evictions.length} block
            {assembly.evictions.length > 1 ? "s" : ""} left out of this request:{" "}
            {assembly.evictions.map((e) => `${e.label} (${e.reason})`).join(" · ")}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
