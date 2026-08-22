// Section 5.6: the GPU drawing this is the GPU running the model. Every frame spent here is a
// token not generated, so the frame budget is explicit and enforced rather than assumed.
import { useEffect, useState } from "react";

export const TARGET_FPS = { streaming: 30, idle: 60 } as const;
export const IDLE_DEMAND_MS = 20_000;
/** Render the background at half resolution and let the compositor upscale it. */
export const BACKGROUND_DPR = 0.5;

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return reduced;
}

/** True once the user has been still for IDLE_DEMAND_MS; the render loop stops until they move. */
export function useIdleAfter(ms: number = IDLE_DEMAND_MS): boolean {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    let timer = window.setTimeout(() => setIdle(true), ms);
    const wake = () => {
      setIdle(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setIdle(true), ms);
    };
    const events = ["pointermove", "pointerdown", "keydown", "wheel", "focus"] as const;
    for (const name of events) window.addEventListener(name, wake, { passive: true });
    return () => {
      window.clearTimeout(timer);
      for (const name of events) window.removeEventListener(name, wake);
    };
  }, [ms]);
  return idle;
}
