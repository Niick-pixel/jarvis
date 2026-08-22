import { useEffect } from "react";
import Composer from "./chat/Composer";
import ContextReadout from "./chat/ContextReadout";
import ErrorBanner from "./chat/ErrorBanner";
import MessageList from "./chat/MessageList";
import StatusBar from "./chat/StatusBar";
import Background from "./scene/Background";
import EdgeGlow from "./scene/EdgeGlow";
import { useSession } from "./store/session";
import { useVisual } from "./store/visual";

export default function App() {
  const bootstrap = useSession((s) => s.bootstrap);
  const preset = useVisual((s) => s.preset);
  const performanceMode = useVisual((s) => s.performanceMode);
  const setPreset = useVisual((s) => s.setPreset);
  const setPerformanceMode = useVisual((s) => s.setPerformanceMode);

  useEffect(() => {
    void bootstrap().catch(() => undefined);
  }, [bootstrap]);

  return (
    <>
      <Background preset={preset} performanceMode={performanceMode} />
      <EdgeGlow />
      <div className="relative z-10 flex h-full flex-col">
        <div className="scrim">
          <StatusBar
            preset={preset}
            onPreset={setPreset}
            performanceMode={performanceMode}
            onPerformanceMode={setPerformanceMode}
          />
        </div>
        <main className="flex min-h-0 flex-1 flex-col">
          <MessageList />
        </main>
        <div className="scrim">
          <ErrorBanner />
          <ContextReadout />
          <Composer />
        </div>
      </div>
    </>
  );
}
