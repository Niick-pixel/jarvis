// One store slice for the conversation and the run attached to it. Kept deliberately small:
// the server owns the truth, this holds what is on screen.
import { create } from "zustand";
import { api } from "../api/client";
import { startChatStream, type ChatRequestBody } from "../api/stream";
import type { ContextAssembly, Conversation, ErrorBody, Message, Remedy } from "../api/types";
import { useVisual } from "./visual";

export type VisualState = "idle" | "listening" | "thinking" | "streaming" | "error";

interface SessionState {
  conversation: Conversation | null;
  messages: Message[];
  activePath: string[];
  assembly: ContextAssembly | null;
  runId: string | null;
  streamingId: string | null;
  streamingText: string;
  tokenTick: number;
  visual: VisualState;
  error: ErrorBody | null;
  tps: number;

  bootstrap: () => Promise<void>;
  refreshTree: () => Promise<void>;
  openConversation: (id: string) => Promise<void>;
  lastPrompt: string | null;
  send: (content: string, ctxLen?: number | null) => Promise<void>;
  continueFrom: (messageId: string) => Promise<void>;
  rerun: (messageId: string) => Promise<void>;
  runStream: (body: ChatRequestBody) => Promise<void>;
  applyRemedy: (remedy: Remedy) => Promise<void>;
  stop: () => Promise<void>;
  dismissError: () => void;
}

export const useSession = create<SessionState>((set, get) => ({
  conversation: null,
  messages: [],
  activePath: [],
  assembly: null,
  runId: null,
  streamingId: null,
  streamingText: "",
  tokenTick: 0,
  visual: "idle",
  error: null,
  tps: 0,
  lastPrompt: null,

  bootstrap: async () => {
    const existing = await api.listConversations();
    const conversation = existing[0] ?? (await api.createConversation("New conversation"));
    const tree = await api.tree(conversation.id);
    set({
      conversation: tree.conversation,
      messages: tree.messages,
      activePath: tree.active_path,
    });
  },

  openConversation: async (id: string) => {
    const tree = await api.tree(id);
    set({
      conversation: tree.conversation,
      messages: tree.messages,
      activePath: tree.active_path,
      assembly: null,
      streamingText: "",
      streamingId: null,
      error: null,
      visual: "idle",
    });
  },

  refreshTree: async () => {
    const conversation = get().conversation;
    if (!conversation) return;
    const tree = await api.tree(conversation.id);
    set({
      conversation: tree.conversation,
      messages: tree.messages,
      activePath: tree.active_path,
    });
  },

  send: async (content: string, ctxLen: number | null = null) => {
    const conversation = get().conversation;
    if (!conversation || get().runId) return;
    set({ lastPrompt: content });
    await get().runStream({ conversation_id: conversation.id, content, ctx_len: ctxLen });
  },

  /** Continue an assistant message you edited: its text becomes the prefix (BRIEF.md 4.1). */
  continueFrom: async (messageId: string) => {
    const conversation = get().conversation;
    if (!conversation || get().runId) return;
    await get().runStream({ conversation_id: conversation.id, continue_from: messageId });
  },

  /** Replay a message with its own recorded seed and params, as a sibling (BRIEF.md 4.5). */
  rerun: async (messageId: string) => {
    const conversation = get().conversation;
    if (!conversation || get().runId) return;
    await get().runStream({ conversation_id: conversation.id, rerun_of: messageId });
  },

  runStream: async (body) => {
    set({ visual: "thinking", error: null, streamingText: "", assembly: null });
    await startChatStream(
      body,
      {
        onEvent: (event) => {
          switch (event.type) {
            case "assembly":
              set({ assembly: event.assembly });
              break;
            case "run":
              set({ runId: event.run_id, streamingId: event.message_id, visual: "streaming" });
              // The user turn and the assistant row both exist on the server by now. Pull them
              // rather than inventing local ids, so what is on screen is what is on disk.
              void get()
                .refreshTree()
                .catch(() => undefined);
              break;
            case "token":
              set((s) => ({
                streamingText: s.streamingText + event.text,
                tokenTick: s.tokenTick + 1,
              }));
              break;
            case "usage":
              set({ tps: event.tps });
              break;
            case "error":
              set({ error: event.error, visual: "error" });
              break;
            case "done":
              break;
          }
        },
        onFailure: (error) => set({ error, visual: "error" }),
        onClose: async () => {
          await get().refreshTree().catch(() => undefined);
          set((s) => ({
            runId: null,
            streamingId: null,
            streamingText: "",
            visual: s.visual === "error" ? "error" : "idle",
          }));
        },
      },
    );
  },

  stop: async () => {
    const runId = get().runId;
    if (runId) await api.stopRun(runId).catch(() => undefined);
  },

  /** Turn the backend's machine-readable remedy into the one action it describes. */
  applyRemedy: async (remedy: Remedy) => {
    const prompt = get().lastPrompt;
    set({ error: null, visual: "idle" });
    switch (remedy.action) {
      case "enable_performance_mode":
        useVisual.getState().setPerformanceMode(true);
        return;
      case "reduce_context": {
        const ctxLen = Number(remedy.params?.ctx_len ?? 0) || null;
        if (prompt) await get().send(prompt, ctxLen);
        return;
      }
      case "retry":
        if (prompt) await get().send(prompt);
        return;
      case "choose_model":
        return;
    }
  },

  dismissError: () => set({ error: null, visual: "idle" }),
}));
