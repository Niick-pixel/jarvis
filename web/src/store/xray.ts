// Token-level uncertainty, and rewriting it (BRIEF.md 4.3).
import { create } from "zustand";
import { api } from "../api/client";
import type { MessageTokens } from "../api/types";
import { useSession } from "./session";

interface XrayState {
  enabled: Record<string, boolean>;
  data: Record<string, MessageTokens>;
  loading: Record<string, boolean>;

  toggle: (messageId: string) => Promise<void>;
  load: (messageId: string) => Promise<void>;
  force: (messageId: string, tokenIdx: number, token: string) => Promise<void>;
}

export const useXray = create<XrayState>((set, get) => ({
  enabled: {},
  data: {},
  loading: {},

  toggle: async (messageId) => {
    const next = !get().enabled[messageId];
    set((s) => ({ enabled: { ...s.enabled, [messageId]: next } }));
    if (next && !get().data[messageId]) await get().load(messageId);
  },

  load: async (messageId) => {
    set((s) => ({ loading: { ...s.loading, [messageId]: true } }));
    try {
      const data = await api.messageTokens(messageId);
      set((s) => ({ data: { ...s.data, [messageId]: data } }));
    } finally {
      set((s) => ({ loading: { ...s.loading, [messageId]: false } }));
    }
  },

  /** Truncate at this token, force a different one, and let generation carry on from there. */
  force: async (messageId, tokenIdx, token) => {
    const conversation = useSession.getState().conversation;
    if (!conversation) return;
    await useSession.getState().runStream({
      conversation_id: conversation.id,
      force_token: { message_id: messageId, token_idx: tokenIdx, token },
    });
  },
}));
