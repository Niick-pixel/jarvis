// Chooses what the background actually is. The shader canvas is loaded lazily so that turning on
// Performance mode - or having reduced motion set - costs nothing to download and nothing to run.
import { Suspense, lazy } from "react";
import FallbackGradient from "./FallbackGradient";
import { usePrefersReducedMotion } from "./perf";
import type { PresetName } from "./presets";

const WarpCanvas = lazy(() => import("./WarpCanvas"));

export default function Background({
  preset,
  performanceMode,
}: {
  preset: PresetName;
  performanceMode: boolean;
}) {
  const reducedMotion = usePrefersReducedMotion();

  if (reducedMotion || performanceMode) return <FallbackGradient preset={preset} />;

  return (
    <Suspense fallback={<FallbackGradient preset={preset} />}>
      <WarpCanvas preset={preset} />
    </Suspense>
  );
}
