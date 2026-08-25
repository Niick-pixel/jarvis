// The Sovereign HUD (BRIEF.md 4.10). A vanity metric, and extremely satisfying, which is the point.
// Fields NVML does not expose show a dash — under WSL2 that is usually power and temperature.
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HudSample, LifetimeCounters } from "../api/types";
import { useSession } from "../store/session";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col">
      <span className="font-mono text-[12px] text-ink">{value}</span>
      <span className="text-[9px] uppercase tracking-wide text-ink-faint">{label}</span>
    </span>
  );
}

export default function Hud() {
  const [open, setOpen] = useState(false);
  const [sample, setSample] = useState<HudSample | null>(null);
  const [counters, setCounters] = useState<LifetimeCounters | null>(null);
  const tps = useSession((s) => s.tps);

  useEffect(() => {
    if (!open) return;
    const source = new EventSource("/api/hud/stream");
    source.addEventListener("hud", (event) =>
      setSample(JSON.parse((event as MessageEvent<string>).data) as HudSample),
    );
    void api.hudCounters().then(setCounters).catch(() => undefined);
    return () => source.close();
  }, [open]);

  const gpu = sample?.gpu;
  const dash = (value: number | null | undefined, unit: string) =>
    value == null ? "—" : `${Math.round(value)}${unit}`;

  return (
    <>
      <Button onClick={() => setOpen(!open)} variant={open ? "primary" : "ghost"} title="Hardware">
        HUD
      </Button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={SPRING}
            className="glass absolute right-4 top-14 z-40 flex gap-5 rounded-2xl px-4 py-3"
          >
            {gpu ? (
              <>
                <Stat label="vram" value={`${gpu.vram_used_mb}/${gpu.vram_total_mb} MB`} />
                <Stat label="gpu" value={dash(gpu.utilization_pct, "%")} />
                <Stat label="temp" value={dash(gpu.temperature_c, "°C")} />
                <Stat label="power" value={dash(gpu.power_w, "W")} />
              </>
            ) : (
              <Stat label="gpu" value="none detected" />
            )}
            <Stat
              label="ram"
              value={sample ? `${sample.ram_used_mb}/${sample.ram_total_mb} MB` : "—"}
            />
            <Stat label="tok/s" value={tps > 0 ? tps.toFixed(1) : "—"} />
            {counters && (
              <>
                <Stat label="lifetime tokens" value={counters.tokens_generated.toLocaleString()} />
                <Stat
                  label={`api cost avoided @ $${counters.rate_per_million_usd}/M`}
                  value={`$${counters.cost_avoided_usd.toFixed(2)}`}
                />
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
