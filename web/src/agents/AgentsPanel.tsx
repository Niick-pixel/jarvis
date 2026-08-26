// Ambient agents (BRIEF.md 4.9): what runs on a schedule, what it reported, and what it did.
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useAgents } from "../store/agents";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";
import AuditLog from "./AuditLog";
import Inbox from "./Inbox";
import JobList from "./JobList";

const TABS = ["Jobs", "Inbox", "Audit"] as const;
type Tab = (typeof TABS)[number];

export default function AgentsPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("Jobs");
  const error = useAgents((s) => s.error);
  const dismiss = useAgents((s) => s.dismiss);
  const refresh = useAgents((s) => s.refresh);
  const unread = useAgents((s) => s.inbox.filter((i) => !i.read_at).length);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  return (
    <motion.aside
      initial={{ x: 24, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 24, opacity: 0 }}
      transition={SPRING}
      className="scrim flex h-full w-[30rem] shrink-0 flex-col border-l border-white/8"
    >
      <div className="flex items-center gap-1 px-3 py-3">
        {TABS.map((name) => (
          <Button
            key={name}
            variant={tab === name ? "primary" : "ghost"}
            onClick={() => setTab(name)}
          >
            {name}
            {name === "Inbox" && unread > 0 ? ` · ${unread}` : ""}
          </Button>
        ))}
        <div className="ml-auto">
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
      {error && (
        <div className="mx-3 mb-2 flex items-start gap-2 rounded-xl bg-rose-400/10 px-3 py-2 text-sm text-rose-100">
          <span className="min-w-0 flex-1">{error}</span>
          <button onClick={dismiss} className="rounded px-2 hover:bg-white/10">
            dismiss
          </button>
        </div>
      )}
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        {tab === "Jobs" && <JobList />}
        {tab === "Inbox" && <Inbox />}
        {tab === "Audit" && <AuditLog />}
      </div>
    </motion.aside>
  );
}
