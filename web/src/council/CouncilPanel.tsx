// The Council (BRIEF.md 4.6): one question, several models, a judge that never sees the names.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ScoreboardRow } from "../api/types";
import { useLibrary } from "../store/library";
import { useCouncil } from "../store/council";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";
import AgreementMatrix from "./AgreementMatrix";

function Scoreboard({ rows }: { rows: ScoreboardRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
        Scoreboard by category
      </p>
      <table className="w-full text-[11px]">
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.model_id}-${row.category}`}>
              <td className="py-0.5 pr-2 text-ink-faint">{row.category}</td>
              <td className="truncate py-0.5 pr-2 font-mono text-ink">
                {row.model_id.split(":").pop()}
              </td>
              <td className="py-0.5 text-right font-mono text-ink-muted">
                {row.wins}/{row.appearances}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CouncilPanel({ onClose }: { onClose: () => void }) {
  const [question, setQuestion] = useState("");
  const [category, setCategory] = useState("general");
  const [scores, setScores] = useState<ScoreboardRow[]>([]);
  const models = useLibrary((s) => s.models);
  const refreshModels = useLibrary((s) => s.refreshModels);
  const [picked, setPicked] = useState<string[]>([]);
  const council = useCouncil();

  useEffect(() => {
    void refreshModels().catch(() => undefined);
    void api.scoreboard().then(setScores).catch(() => undefined);
  }, [refreshModels]);

  const labels = council.members.map((m) => m.label);
  const byLabel = (label: string) =>
    council.answers[label]?.content || council.streaming[label] || "";

  const start = async () => {
    await council.run(question, picked, category);
    void api.scoreboard().then(setScores).catch(() => undefined);
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      transition={SPRING}
      className="scrim absolute inset-0 z-30 flex flex-col overflow-hidden"
    >
      <header className="flex flex-wrap items-center gap-2 px-4 py-3">
        <span className="text-xs uppercase tracking-wide text-ink-faint">Council</span>
        {council.mode && (
          <span className="rounded-full bg-white/8 px-2 py-0.5 text-[10px] text-ink-muted">
            {council.mode}
          </span>
        )}
        <Button onClick={onClose} title="Back to the conversation">
          ✕
        </Button>
      </header>

      <div className="flex flex-wrap items-center gap-2 px-4 pb-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void start();
          }}
          placeholder="Ask every model the same thing…"
          className="min-w-[18rem] flex-1 rounded-xl border border-white/12 bg-black/25 px-3 py-1.5 text-[13px] text-ink outline-none placeholder:text-ink-faint"
        />
        <input
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          title="Scoreboard category — win rates are tracked per kind of task"
          className="w-28 rounded-xl border border-white/12 bg-black/25 px-3 py-1.5 text-[12px] text-ink outline-none"
        />
        <Button variant="primary" onClick={() => void start()} disabled={council.running}>
          {council.running ? "Running…" : "Convene"}
        </Button>
      </div>

      <div className="flex flex-wrap gap-1 px-4 pb-2">
        {models.map((option) => {
          const on = picked.includes(option.model.id);
          return (
            <button
              key={option.model.id}
              onClick={() =>
                setPicked(
                  on
                    ? picked.filter((id) => id !== option.model.id)
                    : [...picked, option.model.id],
                )
              }
              className={`rounded-lg border px-2 py-0.5 text-[11px] ${
                on ? "border-white/25 bg-white/10 text-ink" : "border-white/10 text-ink-faint"
              }`}
              title={option.reason}
            >
              {option.model.display_name}
            </button>
          );
        })}
        {picked.length === 0 && (
          <span className="self-center text-[10px] text-ink-faint">
            none selected — every reachable model takes part
          </span>
        )}
      </div>

      {council.detail && (
        <p className="px-4 pb-2 text-[11px] text-amber-200/80">{council.detail}</p>
      )}
      {council.error && <p className="px-4 pb-2 text-[11px] text-rose-200">{council.error}</p>}

      <div className="scroll-thin flex flex-1 gap-3 overflow-auto px-4 pb-4">
        {labels.map((label) => {
          const answer = council.answers[label];
          return (
            <article
              key={label}
              className="glass flex max-h-full min-w-[18rem] flex-1 flex-col rounded-2xl p-3"
            >
              <header className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-ink-faint">
                <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-ink">{label}</span>
                <span className="truncate">
                  {council.members.find((m) => m.label === label)?.model_id.split(":").pop()}
                </span>
                {answer && <span className="ml-auto">{answer.gen_ms}ms</span>}
              </header>
              {answer?.error ? (
                <p className="text-[12px] text-rose-200">{answer.error}</p>
              ) : (
                <p className="scroll-thin overflow-auto whitespace-pre-wrap text-[13px] text-ink-muted">
                  {byLabel(label) || "waiting for its turn…"}
                </p>
              )}
            </article>
          );
        })}
      </div>

      <AnimatePresence>
        {(council.verdict || council.agreement.length > 0) && (
          <motion.footer
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={SPRING}
            className="flex flex-wrap gap-6 border-t border-white/8 px-4 py-3"
          >
            <AgreementMatrix
              cells={council.agreement}
              labels={labels}
              detail={council.agreementDetail}
            />
            {council.verdict && (
              <div className="min-w-[20rem] flex-1">
                <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
                  Verdict · judged blind as {labels.join(", ")}
                </p>
                <p className="mb-2 font-mono text-[12px] text-ink">
                  {council.verdict.ranking.map((r) => r.label).join(" > ") || "no ranking parsed"}
                </p>
                {council.verdict.disagreements && (
                  <p className="mb-2 text-[12px] text-amber-200/90">
                    {council.verdict.disagreements}
                  </p>
                )}
                <p className="whitespace-pre-wrap text-[13px] text-ink-muted">
                  {council.verdict.synthesis}
                </p>
              </div>
            )}
            <div className="min-w-[14rem]">
              <Scoreboard rows={scores} />
            </div>
          </motion.footer>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
