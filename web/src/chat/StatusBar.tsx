import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProviderInfo } from "../api/types";
import { PRESETS, type PresetName } from "../scene/presets";
import { useAgents } from "../store/agents";
import { useSession } from "../store/session";
import Button from "../ui/Button";
import Hud from "../hud/Hud";
import ModelPicker from "./ModelPicker";

interface Props {
  preset: PresetName;
  onPreset: (preset: PresetName) => void;
  performanceMode: boolean;
  onPerformanceMode: (value: boolean) => void;
  onToggleSidebar: () => void;
  onToggleMemory: () => void;
  onToggleSources: () => void;
  onToggleCouncil: () => void;
  onToggleAgents: () => void;
}

export default function StatusBar({
  preset,
  onPreset,
  performanceMode,
  onPerformanceMode,
  onToggleSidebar,
  onToggleMemory,
  onToggleSources,
  onToggleCouncil,
  onToggleAgents,
}: Props) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const tps = useSession((s) => s.tps);
  const waiting = useAgents((s) => s.pending.length);
  const unread = useAgents((s) => s.inbox.filter((i) => !i.read_at).length);

  useEffect(() => {
    const load = () => void api.providers().then(setProviders).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const online = providers.filter((p) => p.online);
  const names = Object.keys(PRESETS) as PresetName[];

  return (
    <header className="flex w-full flex-wrap items-center gap-2 px-4 py-3 text-xs text-ink-muted">
      <Button onClick={onToggleSidebar} title="Saved conversations">
        ☰
      </Button>
      <span className="font-medium text-ink">Jarvis</span>
      <span
        className={`rounded-full px-2 py-0.5 ${
          online.length ? "bg-emerald-400/15 text-emerald-200" : "bg-rose-400/15 text-rose-200"
        }`}
        title={providers.map((p) => `${p.name}: ${p.online ? "online" : p.detail}`).join("\n")}
      >
        {online.length ? online.map((p) => p.name).join(", ") : "no backend reachable"}
      </span>
      {tps > 0 && <span>{tps.toFixed(1)} tok/s</span>}

      <div className="ml-auto flex items-center gap-1">
        <Button
          onClick={onToggleAgents}
          variant={waiting > 0 ? "primary" : "ghost"}
          title={
            waiting > 0
              ? `${waiting} tool call${waiting === 1 ? "" : "s"} waiting for you`
              : "Scheduled jobs, their inbox, and the audit log"
          }
        >
          Agents{waiting > 0 ? ` · ${waiting}!` : unread > 0 ? ` · ${unread}` : ""}
        </Button>
        <Button onClick={onToggleCouncil} title="Ask several models the same question">
          Council
        </Button>
        <Button onClick={onToggleSources} title="Folders indexed for retrieval">
          Knowledge
        </Button>
        <Button onClick={onToggleMemory} title="What the app remembers about you">
          Memory
        </Button>
        <Hud />
        <ModelPicker />
        <span className="mx-1 h-4 w-px bg-white/10" />
        {names.map((name) => (
          <Button
            key={name}
            onClick={() => onPreset(name)}
            variant={preset === name ? "primary" : "ghost"}
          >
            {PRESETS[name].name}
          </Button>
        ))}
        <Button
          onClick={() => onPerformanceMode(!performanceMode)}
          variant={performanceMode ? "primary" : "ghost"}
          title="Swap the shader for a CSS gradient and hand the VRAM back to the model"
        >
          Performance
        </Button>
      </div>
    </header>
  );
}
