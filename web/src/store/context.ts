// The Context Inspector's state: what would go in next, and the preferences that shape it.
import { create } from "zustand";
import { api } from "../api/client";
import type { ContextAssembly } from "../api/types";
import { useSession } from "./session";

interface ContextState {
  preview: ContextAssembly | null;
  busy: boolean;

  refresh: () => Promise<void>;
  toggle: (sourceRef: string, disabled: boolean) => Promise<void>;
  pin: (sourceRef: string, pinned: boolean) => Promise<void>;
  move: (sourceRef: string, ord: number) => Promise<void>;
}

export const useContextInspector = create<ContextState>((set, get) => ({
  preview: null,
  busy: false,

  /** Assemble without generating, so the bar is live before you press send. */
  refresh: async () => {
    const conversation = useSession.getState().conversation;
    if (!conversation) return;
    set({ busy: true });
    try {
      set({ preview: await api.previewContext(conversation.id) });
    } finally {
      set({ busy: false });
    }
  },

  toggle: async (sourceRef, disabled) => {
    await write(sourceRef, { disabled });
    await get().refresh();
  },

  pin: async (sourceRef, pinned) => {
    await write(sourceRef, { pinned });
    await get().refresh();
  },

  move: async (sourceRef, ord) => {
    await write(sourceRef, { ord });
    await get().refresh();
  },
}));

/** Writes the block's whole preference, not just the field being changed.
 *
 * The server stores one row per block, so sending a partial patch would reset the fields it
 * omitted - pinning something would quietly un-exclude it. Merge with what is on screen first.
 */
async function write(
  sourceRef: string,
  patch: { disabled?: boolean; pinned?: boolean; ord?: number },
): Promise<void> {
  const conversation = useSession.getState().conversation;
  if (!conversation) return;
  const current = useContextInspector
    .getState()
    .preview?.blocks.find((b) => b.source_ref === sourceRef);
  await api.setBlockPrefs(conversation.id, [
    {
      source_ref: sourceRef,
      pinned: patch.pinned ?? current?.pinned ?? false,
      disabled: patch.disabled ?? (current ? !current.included : false),
      ...(patch.ord !== undefined ? { ord: patch.ord } : {}),
    },
  ]);
}
