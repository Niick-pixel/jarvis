// The jobs themselves, with the last thing each one did. "Run now" uses the same code path the
// scheduler does, so testing a job is testing the job.
import { useState } from "react";
import type { Job, JobRun } from "../api/types";
import { useAgents } from "../store/agents";
import Button from "../ui/Button";
import JobForm from "./JobForm";

const STATUS_STYLE: Record<string, string> = {
  running: "text-sky-200",
  waiting_approval: "text-amber-200",
  done: "text-emerald-200",
  failed: "text-rose-200",
  cancelled: "text-ink-faint",
};

function when(ms: number | null | undefined): string {
  if (!ms) return "never";
  return new Date(ms).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

export default function JobList() {
  const jobs = useAgents((s) => s.jobs);
  const runs = useAgents((s) => s.runs);
  const tools = useAgents((s) => s.tools);
  const busy = useAgents((s) => s.busy);
  const runNow = useAgents((s) => s.runNow);
  const toggle = useAgents((s) => s.toggle);
  const remove = useAgents((s) => s.remove);
  const [adding, setAdding] = useState(false);

  const lastRun = (job: Job): JobRun | undefined => runs.find((r) => r.job_id === job.id);

  if (adding) return <JobForm tools={tools} onDone={() => setAdding(false)} />;

  return (
    <div className="flex flex-col gap-2 px-3 py-2">
      <Button onClick={() => setAdding(true)}>New job</Button>
      {jobs.length === 0 && (
        <p className="py-4 text-sm text-ink-faint">
          No jobs. A job is a prompt, a cron line, and the tools you are willing to let it use.
        </p>
      )}
      {jobs.map((job) => {
        const run = lastRun(job);
        return (
          <article key={job.id} className="glass rounded-xl p-3 text-sm">
            <div className="flex items-baseline gap-2">
              <h3 className="min-w-0 flex-1 truncate text-ink">{job.name}</h3>
              <code className="text-xs text-ink-faint">{job.cron}</code>
            </div>
            <p className="mt-1 text-xs text-ink-faint">
              next {job.enabled ? when(job.next_run_at) : "paused"} · last {when(job.last_run_at)}
            </p>
            <p className="mt-1 text-xs text-ink-muted">
              {job.tools.length ? job.tools.join(", ") : "no tools"}
              {job.workspace ? ` · writes in ${job.workspace}` : " · cannot write"}
            </p>
            {run && (
              <p className={`mt-2 text-xs ${STATUS_STYLE[run.status] ?? ""}`}>
                {run.status.replace("_", " ")}
                {run.summary ? `: ${run.summary}` : ""}
                {run.error ? `: ${run.error}` : ""}
              </p>
            )}
            <div className="mt-2 flex flex-wrap justify-end gap-1">
              <Button disabled={busy === job.id} onClick={() => void runNow(job.id)}>
                Run now
              </Button>
              <Button onClick={() => void toggle(job)}>{job.enabled ? "Pause" : "Resume"}</Button>
              <Button onClick={() => void remove(job.id)}>Delete</Button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
