// Word-level diff between a rerun and the message it replayed (BRIEF.md 4.5).
// With the same seed the two are identical, which is the point: a difference means a parameter
// changed, not that the model wandered.
import { diffWords } from "diff";
import { useMemo } from "react";
import type { Message } from "../api/types";

export default function ReplayDiff({
  message,
  original,
}: {
  message: Message;
  original: Message | undefined;
}) {
  const parts = useMemo(
    () => (original ? diffWords(original.content, message.content) : []),
    [original, message.content],
  );

  if (!original) {
    return <p className="text-[11px] text-ink-faint">The message this replayed is not loaded.</p>;
  }
  const changed = parts.some((part) => part.added || part.removed);

  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <p className="mb-2 text-[10px] uppercase tracking-wide text-ink-faint">
        {changed ? "differences from the original" : "byte-identical to the original"}
      </p>
      <p className="whitespace-pre-wrap text-[13px] leading-relaxed">
        {parts.map((part, index) => (
          <span
            key={index}
            className={
              part.added
                ? "bg-emerald-400/20 text-emerald-100"
                : part.removed
                  ? "bg-rose-400/20 text-rose-100 line-through"
                  : "text-ink-muted"
            }
          >
            {part.value}
          </span>
        ))}
      </p>
    </div>
  );
}
