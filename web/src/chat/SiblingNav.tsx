// The inline `< 2/4 >` switcher. Every edit and every rerun leaves a sibling here, so this is
// how you get back to a version you moved away from - nothing is ever gone.
import { useEffect } from "react";
import { useGraph } from "../store/graph";

export default function SiblingNav({ messageId }: { messageId: string }) {
  const siblings = useGraph((s) => s.siblings[messageId]);
  const loadSiblings = useGraph((s) => s.loadSiblings);
  const switchTo = useGraph((s) => s.switchTo);

  useEffect(() => {
    if (!siblings) void loadSiblings([messageId]).catch(() => undefined);
  }, [messageId, siblings, loadSiblings]);

  if (!siblings || siblings.ids.length < 2) return null;

  const go = (delta: number) => {
    const next = siblings.ids[(siblings.index + delta + siblings.ids.length) % siblings.ids.length];
    if (next) void switchTo(next);
  };

  return (
    <span className="inline-flex items-center gap-1 rounded-lg bg-white/6 px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
      <button onClick={() => go(-1)} className="px-1 hover:text-ink" title="Previous version">
        ‹
      </button>
      <span>
        {siblings.index + 1}/{siblings.ids.length}
      </span>
      <button onClick={() => go(1)} className="px-1 hover:text-ink" title="Next version">
        ›
      </button>
    </span>
  );
}
