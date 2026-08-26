// Scheduled jobs, the approval queue, and the inbox.
//
// This polls. Jobs fire on a cron and approvals appear while you are looking at something else,
// and there is no push channel for either - adding one would mean a second SSE stream and a
// reconnect story for a payload that is three integers. Five seconds against loopback costs
// nothing measurable.
import { create } from "zustand";
import { ApiError, api } from "../api/client";
import type { InboxItem, Job, JobCreate, JobRun, PendingCall, ToolInfo } from "../api/types";

const POLL_MS = 5_000;
let timer: number | null = null;

interface AgentsState {
  jobs: Job[];
  runs: JobRun[];
  inbox: InboxItem[];
  pending: PendingCall[];
  tools: ToolInfo[];
  error: string | null;
  busy: string | null;

  refresh: () => Promise<void>;
  poll: () => Promise<void>;
  watch: () => () => void;
  create: (body: JobCreate) => Promise<boolean>;
  toggle: (job: Job) => Promise<void>;
  remove: (jobId: string) => Promise<void>;
  runNow: (jobId: string) => Promise<void>;
  decide: (callId: string, approve: boolean, grant: boolean) => Promise<void>;
  markRead: (itemId: string, read: boolean) => Promise<void>;
  dismiss: () => void;
}

export const useAgents = create<AgentsState>((set, get) => ({
  jobs: [],
  runs: [],
  inbox: [],
  pending: [],
  tools: [],
  error: null,
  busy: null,

  refresh: async () => {
    const [jobs, runs, inbox, pending, tools] = await Promise.all([
      api.jobs(),
      api.jobRuns(),
      api.inbox(),
      api.toolCalls(true),
      api.toolCatalogue(),
    ]);
    set({ jobs, runs, inbox, pending, tools });
  },

  /** The cheap half, on a timer: what is waiting on you and what has landed. */
  poll: async () => {
    const [pending, inbox, runs] = await Promise.all([
      api.toolCalls(true),
      api.inbox(),
      api.jobRuns(),
    ]);
    set({ pending, inbox, runs });
  },

  watch: () => {
    void get().refresh().catch(() => undefined);
    if (timer === null) {
      timer = window.setInterval(() => void get().poll().catch(() => undefined), POLL_MS);
    }
    return () => {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
    };
  },

  create: async (body: JobCreate) => {
    try {
      await api.createJob(body);
      await get().refresh();
      return true;
    } catch (error) {
      set({ error: message(error) });
      return false;
    }
  },

  toggle: async (job: Job) => {
    await api.patchJob(job.id, { enabled: !job.enabled }).catch((e) => set({ error: message(e) }));
    await get().refresh().catch(() => undefined);
  },

  remove: async (jobId: string) => {
    await api.deleteJob(jobId).catch((e) => set({ error: message(e) }));
    await get().refresh().catch(() => undefined);
  },

  runNow: async (jobId: string) => {
    set({ busy: jobId, error: null });
    try {
      await api.runJob(jobId);
      await get().poll();
    } catch (error) {
      set({ error: message(error) });
    } finally {
      set({ busy: null });
    }
  },

  decide: async (callId: string, approve: boolean, grant: boolean) => {
    set({ busy: callId });
    try {
      await api.decideCall(callId, { approve, grant });
      await get().poll();
    } catch (error) {
      set({ error: message(error) });
    } finally {
      set({ busy: null });
    }
  },

  markRead: async (itemId: string, read: boolean) => {
    const item = await api.markInboxRead(itemId, read).catch(() => null);
    if (item) set((s) => ({ inbox: s.inbox.map((i) => (i.id === item.id ? item : i)) }));
  },

  dismiss: () => set({ error: null }),
}));

function message(error: unknown): string {
  if (error instanceof ApiError) return error.body.message;
  return error instanceof Error ? error.message : String(error);
}
