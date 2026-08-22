import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProviderInfo } from "../api/types";
import { PRESETS, type PresetName } from "../scene/presets";
import { useSession } from "../store/session";
import Button from "../ui/Button";

interface Props {
  preset: PresetName;
  onPreset: (preset: PresetName) => void;
  performanceMode: boolean;
  onPerformanceMode: (value: boolean) => void;
}

export default function StatusBar({
  preset,
  onPreset,
  performanceMode,
  onPerformanceMode,
}: Props) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const tps = useSession((s) => s.tps);

  useEffect(() => {
    const load = () => void api.providers().then(setProviders).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const online = providers.filter((p) => p.online);
  const names = Object.keys(PRESETS) as PresetName[];

  return (
    <header className="mx-auto flex w-full max-w-4xl items-center gap-3 px-6 pt-5 text-xs text-ink-muted">
      <span className="font-medium text-ink">Jarvis</span>
      <span
        className={`rounded-full px-2 py-0.5 ${
          online.length ? "bg-emerald-400/15 text-emerald-200" : "bg-rose-400/15 text-rose-200"
        }`}
        title={providers.map((p) => `${p.name}: ${p.online ? "online" : p.detail}`).join("\n")}
      >
        {online.length ? `${online.map((p) => p.name).join(", ")}` : "no backend reachable"}
      </span>
      {tps > 0 && <span>{tps.toFixed(1)} tok/s</span>}
      <div className="ml-auto flex items-center gap-1">
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
