import type {
  Conversation,
  ConversationTree,
  ErrorBody,
  HardwareReport,
  Health,
  Message,
  ModelInfo,
  ModelOption,
  ModelRecommendation,
  SelectedModel,
  ProviderInfo,
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
  stopRun: (runId: string) =>
    request<{ status: string }>(`/api/chat/runs/${runId}/stop`, { method: "POST" }),
};
