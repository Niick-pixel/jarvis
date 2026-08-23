// Which model is running, why it was chosen, and what this machine can and cannot hold.
//
// The list is the server's ranking, which is the same ranking the app uses to choose on its own -
// so the picker can never recommend one thing while the app quietly runs another.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { ModelOption } from "../api/types";
import { useLibrary } from "../store/library";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

const BADGE: Record<string, { label: string; className: string }> = {
  fits: { label: "fits", className: "bg-emerald-400/15 text-emerald-200" },
  tight: { label: "tight", className: "bg-amber-400/15 text-amber-200" },
  needs_offload: { label: "too big", className: "bg-rose-400/15 text-rose-200" },
  unavailable: { label: "unknown", className: "bg-white/10 text-ink-faint" },
};

function Row({
  option,
  active,
  onPick,
}: {
  option: ModelOption;
  active: boolean;
  onPick: () => void;
}) {
  const badge = BADGE[option.status] ?? BADGE.unavailable!;
  return (
    <button
      onClick={onPick}
      className={`w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${
        active ? "border-white/25 bg-white/10" : "border-transparent hover:bg-white/6"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="truncate text-sm text-ink">{option.model.display_name}</span>
        <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${badge.className}`}>
          {badge.label}
        </span>
        {option.remote && (
          <span className="rounded-full bg-sky-400/15 px-1.5 py-0.5 text-[10px] text-sky-200">
            remote
          </span>
        )}
        {option.recommended && (
          <span className="ml-auto text-[10px] uppercase tracking-wide text-ink-faint">
            auto pick
          </span>
        )}
      </div>
      <p className="mt-1 text-[11px] leading-snug text-ink-faint">{option.reason}</p>
      {option.budget && (
        <p className="mt-1 font-mono text-[10px] text-ink-faint">
          {option.budget.weights_mb} MB weights + {option.budget.kv_cache_mb} MB KV @{" "}
          {option.recommended_ctx_len / 1024}K + {option.budget.browser_reserve_mb} MB browser ={" "}
          {option.budget.total_required_mb} MB of {option.budget.vram_free_mb} MB free
        </p>
      )}
    </button>
  );
}

export default function ModelPicker() {
  const [open, setOpen] = useState(false);
  const { models, selectedModelId, refreshModels, selectModel } = useLibrary();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refreshModels().catch(() => undefined);
  }, [refreshModels]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!panel.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  const auto = models.find((m) => m.recommended);
  const current = models.find((m) => m.model.id === selectedModelId) ?? auto;
  const label = current?.model.display_name ?? "no model";

  return (
    <div className="relative" ref={panel}>
      <Button
        onClick={() => {
          setOpen(!open);
          if (!open) void refreshModels().catch(() => undefined);
        }}
        title="Choose a model, or let the app pick the best one this machine can hold"
      >
        <span className="max-w-[16rem] truncate">{label}</span>
        {!selectedModelId && <span className="ml-1.5 text-ink-faint">auto</span>}
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={SPRING}
            className="glass absolute right-0 z-40 mt-2 max-h-[70vh] w-[30rem] overflow-y-auto rounded-2xl p-2"
          >
            <button
              onClick={() => {
                void selectModel(null);
                setOpen(false);
              }}
              className={`w-full rounded-xl border px-3 py-2 text-left ${
                selectedModelId ? "border-transparent hover:bg-white/6" : "border-white/25 bg-white/10"
              }`}
            >
              <span className="text-sm text-ink">Automatic</span>
              <p className="mt-0.5 text-[11px] text-ink-faint">
                Pick the largest local model this machine can hold, and re-pick if the backend
                changes. Never selects a remote model on its own.
              </p>
            </button>
            <div className="my-1.5 h-px bg-white/8" />
            {models.length === 0 && (
              <p className="px-3 py-3 text-[11px] text-ink-faint">
                No model is reachable. Start llama.cpp, Ollama or LM Studio, or run{" "}
                <span className="font-mono">make models</span>.
              </p>
            )}
            {models.map((option) => (
              <Row
                key={option.model.id}
                option={option}
                active={option.model.id === selectedModelId}
                onPick={() => {
                  void selectModel(option.model.id);
                  setOpen(false);
                }}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
