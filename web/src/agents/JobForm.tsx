// Creating a job. The tool list is the backend's catalogue, so what you can tick is exactly what
// the model will be told it has - and the ones that stop at the gate say so here too.
import { useState } from "react";
import type { ToolInfo } from "../api/types";
import { useAgents } from "../store/agents";
import Button from "../ui/Button";

const FIELD =
  "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-white/25";

export default function JobForm({ tools, onDone }: { tools: ToolInfo[]; onDone: () => void }) {
  const create = useAgents((s) => s.create);
  const [name, setName] = useState("");
  const [cron, setCron] = useState("0 19 * * *");
  const [prompt, setPrompt] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);

  const submit = async () => {
    if (!name.trim() || !prompt.trim()) return;
    const ok = await create({
      name: name.trim(),
      cron: cron.trim(),
      prompt: prompt.trim(),
      tools: chosen,
      workspace: workspace.trim(),
      enabled: true,
    });
    if (ok) onDone();
  };

  return (
    <div className="flex flex-col gap-2 px-3 py-2">
      <input className={FIELD} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <input
        className={FIELD}
        placeholder="Cron, five fields"
        value={cron}
        onChange={(e) => setCron(e.target.value)}
        title="minute hour day-of-month month day-of-week, in this machine's local time"
      />
      <textarea
        className={`${FIELD} min-h-24 resize-y`}
        placeholder="What should it do? Written as an instruction, the way you would ask a person."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <input
        className={FIELD}
        placeholder="Workspace directory (blank means it cannot write anywhere)"
        value={workspace}
        onChange={(e) => setWorkspace(e.target.value)}
      />
      <fieldset className="rounded-xl border border-white/10 p-2">
        <legend className="px-1 text-[11px] uppercase tracking-wide text-ink-faint">Tools</legend>
        {tools.map((tool) => (
          <label key={tool.name} className="flex items-start gap-2 px-1 py-1 text-sm text-ink-muted">
            <input
              type="checkbox"
              className="mt-1"
              checked={chosen.includes(tool.name)}
              onChange={(e) =>
                setChosen((current) =>
                  e.target.checked
                    ? [...current, tool.name]
                    : current.filter((n) => n !== tool.name),
                )
              }
            />
            <span className="min-w-0">
              <span className="text-ink">{tool.name}</span>
              {tool.side_effect && (
                <span className="ml-2 rounded-full bg-amber-300/15 px-2 py-0.5 text-[11px] text-amber-200">
                  asks first
                </span>
              )}
              <span className="block text-xs text-ink-faint">{tool.summary}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="flex justify-end gap-2">
        <Button onClick={onDone}>Cancel</Button>
        <Button variant="primary" onClick={() => void submit()} disabled={!name.trim() || !prompt.trim()}>
          Create
        </Button>
      </div>
    </div>
  );
}
