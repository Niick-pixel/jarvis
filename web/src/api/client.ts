import type {
  AuditEntry,
  BlockPref,
  ContextAssembly,
  Conversation,
  Decision,
  ConversationTree,
  ErrorBody,
  ExportResult,
  HardwareReport,
  Health,
  InboxItem,
  Job,
  JobCreate,
  JobPatch,
  JobRun,
  IndexProgress,
  LifetimeCounters,
  MemoryBatch,
  MemoryCommit,
  MemoryEntry,
  Message,
  MessageTokens,
  ModelInfo,
  ModelOption,
  ModelRecommendation,
  OpenedChunk,
  PendingCall,
  ProviderInfo,
  RetrievalStatus,
  ScoreboardRow,
  SearchStatus,
  SelectedModel,
  SiblingSet,
  Source,
  SpeakRequest,
  ToolGrant,
  ToolInfo,
  Transcript,
  VoiceStatus,
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
  memory: () => request<MemoryEntry[]>("/api/memory"),
  createMemory: (body: { title: string; content: string; always: boolean }) =>
    request<MemoryEntry>("/api/memory", { method: "POST", body: JSON.stringify(body) }),
  updateMemory: (id: string, body: { title?: string; content?: string; always?: boolean }) =>
    request<MemoryEntry>(`/api/memory/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  forgetMemory: (id: string) =>
    request<{ forgotten: string; remaining: number }>(`/api/memory/${id}`, { method: "DELETE" }),
  memoryHistory: (id: string) => request<MemoryCommit[]>(`/api/memory/${id}/history`),
  captureFor: (messageId: string) =>
    request<MemoryBatch>(`/api/memory/batches/for-message/${messageId}`),
  undoCapture: (batchId: string) =>
    request<{ forgotten: string; remaining: number }>(`/api/memory/batches/${batchId}`, {
      method: "DELETE",
    }),
  sources: () => request<Source[]>("/api/knowledge/sources"),
  addSource: (path: string) =>
    request<Source>("/api/knowledge/sources", { method: "POST", body: JSON.stringify({ path }) }),
  removeSource: (id: string) =>
    request<{ status: string }>(`/api/knowledge/sources/${id}`, { method: "DELETE" }),
  indexSource: (id: string) =>
    request<IndexProgress>(`/api/knowledge/sources/${id}/index`, { method: "POST" }),
  indexProgress: () => request<IndexProgress[]>("/api/knowledge/progress"),
  retrievalStatus: () => request<RetrievalStatus>("/api/knowledge/status"),
  pauseIndexing: (paused: boolean) =>
    request<{ paused: boolean }>(`/api/knowledge/${paused ? "pause" : "resume"}`, {
      method: "POST",
    }),
  openCitation: (ref: string) =>
    request<OpenedChunk>(`/api/knowledge/open?ref=${encodeURIComponent(ref)}`),
  searchStatus: () => request<SearchStatus>("/api/search/status"),
  scoreboard: () => request<ScoreboardRow[]>("/api/council/scoreboard"),
  exportConversation: (conversationId: string) =>
    request<ExportResult>(`/api/conversations/${conversationId}/export`, { method: "POST" }),
  jobs: () => request<Job[]>("/api/agents/jobs"),
  createJob: (body: JobCreate) =>
    request<Job>("/api/agents/jobs", { method: "POST", body: JSON.stringify(body) }),
  patchJob: (jobId: string, body: JobPatch) =>
    request<Job>(`/api/agents/jobs/${jobId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteJob: (jobId: string) =>
    request<{ status: string }>(`/api/agents/jobs/${jobId}`, { method: "DELETE" }),
  runJob: (jobId: string) =>
    request<JobRun>(`/api/agents/jobs/${jobId}/run`, { method: "POST" }),
  jobRuns: (jobId?: string) =>
    request<JobRun[]>(`/api/agents/runs${jobId ? `?job_id=${jobId}` : ""}`),
  runCalls: (runId: string) => request<PendingCall[]>(`/api/agents/runs/${runId}/calls`),
  inbox: () => request<InboxItem[]>("/api/agents/inbox"),
  markInboxRead: (itemId: string, read: boolean) =>
    request<InboxItem>(`/api/agents/inbox/${itemId}/read`, {
      method: "POST",
      body: JSON.stringify({ read }),
    }),
  toolCatalogue: () => request<ToolInfo[]>("/api/tools"),
  toolCalls: (onlyPending = false) =>
    request<PendingCall[]>(`/api/tools/calls?only_pending=${onlyPending}`),
  decideCall: (callId: string, body: Decision) =>
    request<PendingCall>(`/api/tools/calls/${callId}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  grants: () => request<ToolGrant[]>("/api/tools/grants"),
  revokeGrant: (tool: string, scope: string) =>
    request<{ status: string }>(
      `/api/tools/grants?tool=${encodeURIComponent(tool)}&scope=${encodeURIComponent(scope)}`,
      { method: "DELETE" },
    ),
  auditLog: () => request<AuditEntry[]>("/api/audit"),
  voiceStatus: () => request<VoiceStatus>("/api/voice/status"),
  transcribe: (clip: Blob) =>
    request<Transcript>("/api/voice/transcribe", {
      method: "POST",
      body: clip,
      // The recorder's own container type, whatever it chose. The server decodes it, not us.
      headers: { "Content-Type": clip.type || "application/octet-stream" },
    }),
  stopRun: (runId: string) =>
    request<{ status: string }>(`/api/chat/runs/${runId}/stop`, { method: "POST" }),
};

/** The one endpoint whose body is audio rather than JSON, so it needs the raw stream. */
export async function speakStream(
  body: SpeakRequest,
): Promise<ReadableStream<Uint8Array<ArrayBufferLike>>> {
  const response = await fetch("/api/voice/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const error = (await response.json().catch(() => null)) as ErrorBody | null;
    throw new ApiError(
      error ?? { code: "internal", message: `${response.status} ${response.statusText}` },
    );
  }
  return response.body;
}
