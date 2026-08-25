import type {
  BlockPref,
  ContextAssembly,
  Conversation,
  ConversationTree,
  ErrorBody,
  HardwareReport,
  Health,
  LifetimeCounters,
  Message,
  MessageTokens,
  ModelInfo,
  ModelOption,
  ModelRecommendation,
  ProviderInfo,
  SelectedModel,
  SiblingSet,
} from "./types";

export class ApiError extends Error {
  constructor(readonly body: ErrorBody) {
    super(body.message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    // The backend's error envelope carries a remedy the UI can render as a button.
    const body = (await response.json().catch(() => null)) as ErrorBody | null;
    throw new ApiError(
      body ?? { code: "internal", message: `${response.status} ${response.statusText}` },
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  providers: () => request<ProviderInfo[]>("/api/providers"),
  models: () => request<ModelInfo[]>("/api/models"),
  hardware: () => request<HardwareReport>("/api/hardware"),
  modelOptions: () => request<ModelOption[]>("/api/models/options"),
  selectedModel: () => request<SelectedModel>("/api/models/selected"),
  selectModel: (modelId: string | null) =>
    request<SelectedModel>("/api/models/selected", {
      method: "PUT",
      body: JSON.stringify({ model_id: modelId }),
    }),
  catalog: () => request<ModelRecommendation[]>("/api/hardware/catalog"),

  listConversations: () => request<Conversation[]>("/api/conversations"),
  createConversation: (title = "", systemPrompt = "") =>
    request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title, system_prompt: systemPrompt }),
    }),
  tree: (id: string) => request<ConversationTree>(`/api/conversations/${id}`),
  deleteConversation: (id: string) =>
    request<{ status: string }>(`/api/conversations/${id}`, { method: "DELETE" }),
  addMessage: (id: string, content: string, parentId: string | null = null) =>
    request<Message>(`/api/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, role: "user", parent_id: parentId }),
    }),
  editMessage: (id: string, content: string) =>
    request<Message>(`/api/messages/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
  siblings: (id: string) => request<SiblingSet>(`/api/messages/${id}/siblings`),
  setActiveLeaf: (conversationId: string, messageId: string) =>
    request<Conversation>(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify({ active_leaf_id: messageId }),
    }),
  previewContext: (conversationId: string) =>
    request<ContextAssembly>("/api/context/preview", {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId }),
    }),
  setBlockPrefs: (conversationId: string, prefs: BlockPref[]) =>
    request<BlockPref[]>("/api/context/blocks", {
      method: "PATCH",
      body: JSON.stringify({ conversation_id: conversationId, prefs }),
    }),
  messageTokens: (id: string) => request<MessageTokens>(`/api/messages/${id}/tokens`),
  hudCounters: () => request<LifetimeCounters>("/api/hud/counters"),
  nudge: (runId: string, text: string) =>
    request<{ message_id: string; token_idx: number }>(`/api/chat/runs/${runId}/nudge`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  stopRun: (runId: string) =>
    request<{ status: string }>(`/api/chat/runs/${runId}/stop`, { method: "POST" }),
};
