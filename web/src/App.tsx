import { AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import Composer from "./chat/Composer";
import Nudge from "./chat/Nudge";
import ContextBar from "./context/ContextBar";
import Conversations from "./chat/Conversations";
import ErrorBanner from "./chat/ErrorBanner";
import MessageList from "./chat/MessageList";
import Minimap from "./graph/Minimap";
import StatusBar from "./chat/StatusBar";
import SourcesPanel from "./knowledge/SourcesPanel";
import CaptureToast from "./memory/CaptureToast";
import MemoryPage from "./memory/MemoryPage";
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
  const [sidebar, setSidebar] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  useEffect(() => {
    void bootstrap().catch(() => undefined);
  }, [bootstrap]);

  return (
    <>
      <Background preset={preset} performanceMode={performanceMode} />
      <EdgeGlow />
      <div className="relative z-10 flex h-full">
        <AnimatePresence>
          {sidebar && <Conversations onClose={() => setSidebar(false)} />}
        </AnimatePresence>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="scrim relative z-30">
            <StatusBar
              preset={preset}
              onPreset={setPreset}
              performanceMode={performanceMode}
              onPerformanceMode={setPerformanceMode}
              onToggleSidebar={() => setSidebar((open) => !open)}
              onToggleMemory={() => setMemoryOpen((open) => !open)}
              onToggleSources={() => setSourcesOpen((open) => !open)}
            />
          </div>
          <main className="relative flex min-h-0 flex-1 flex-col">
            <Minimap />
            <MessageList />
          </main>
          <div className="scrim">
            <ErrorBanner />
            <ContextBar />
            <Nudge />
            <Composer />
          </div>
        </div>
        <AnimatePresence>
          {sourcesOpen && <SourcesPanel onClose={() => setSourcesOpen(false)} />}
          {memoryOpen && <MemoryPage onClose={() => setMemoryOpen(false)} />}
        </AnimatePresence>
      </div>
      <CaptureToast />
    </>
  );
}
