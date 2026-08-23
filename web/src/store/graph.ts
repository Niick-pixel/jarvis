// Editing the shape of the conversation: forking, switching branches, merging.
// The server owns the tree; this is the thin layer that asks it to change and then re-reads.
import { create } from "zustand";
import { api } from "../api/client";
import type { SiblingSet } from "../api/types";
import { useSession } from "./session";

interface GraphState {
  editing: string | null;
  siblings: Record<string, SiblingSet>;

  beginEdit: (messageId: string) => void;
  cancelEdit: () => void;
  saveEdit: (messageId: string, content: string) => Promise<string | null>;
  switchTo: (messageId: string) => Promise<void>;
  loadSiblings: (messageIds: string[]) => Promise<void>;
}

export const useGraph = create<GraphState>((set, get) => ({
  editing: null,
  siblings: {},

  beginEdit: (messageId) => set({ editing: messageId }),
  cancelEdit: () => set({ editing: null }),

  saveEdit: async (messageId, content) => {
    const forked = await api.editMessage(messageId, content);
    set({ editing: null });
    await useSession.getState().refreshTree();
    await get().loadSiblings([forked.id]);
    return forked.id;
  },

  /** Move the active-leaf pointer. Nothing is created; you are just reading a different branch. */
  switchTo: async (messageId) => {
    const conversation = useSession.getState().conversation;
    if (!conversation) return;
    await api.setActiveLeaf(conversation.id, messageId);
    await useSession.getState().refreshTree();
  },

  loadSiblings: async (messageIds) => {
    const found = await Promise.all(
      messageIds.map(async (id) => [id, await api.siblings(id)] as const),
    );
    set((state) => ({ siblings: { ...state.siblings, ...Object.fromEntries(found) } }));
  },
}));
