// Convenience aliases over the generated schema. Every shape here traces back to a Pydantic
// model on the backend; nothing in this file declares a shape of its own (rule 0.5).
import type { components } from "./schema.gen";

type S = components["schemas"];

export type Conversation = S["Conversation"];
export type ConversationTree = S["ConversationTree"];
export type Message = S["Message"];
export type Role = Message["role"];
export type ContextAssembly = S["ContextAssembly"];
export type ContextBlock = S["ContextBlock"];
export type EvictionNotice = S["EvictionNotice"];
export type ModelInfo = S["ModelInfo"];
export type ModelOption = S["ModelOption"];
export type SelectedModel = S["SelectedModel"];
export type SiblingSet = S["SiblingSet"];
export type BlockPref = S["BlockPref"];
export type ProviderInfo = S["ProviderInfo"];
export type HardwareReport = S["HardwareReport"];
export type ModelRecommendation = S["ModelRecommendation"];
export type VramBudget = S["VramBudget"];
export type SamplingParams = S["SamplingParams"];
export type ErrorBody = S["ErrorBody"];
export type Remedy = S["Remedy"];
export type Health = S["Health"];

export type AssemblyEvent = S["AssemblyEvent"];
export type RunEvent = S["RunEvent"];
export type TokenEvent = S["TokenEvent"];
export type UsageEvent = S["UsageEvent"];
export type DoneEvent = S["DoneEvent"];
export type ErrorEvent = S["ErrorEvent"];

/** The SSE union, exhaustively switchable because the discriminator comes from the backend. */
export type StreamEvent =
  | AssemblyEvent
  | RunEvent
  | TokenEvent
  | UsageEvent
  | DoneEvent
  | ErrorEvent;
export type MessageTokens = S["MessageTokens"];
export type TokenView = S["TokenView"];
export type Alternative = S["Alternative"];
export type NudgeMark = S["NudgeMark"];
export type LifetimeCounters = S["LifetimeCounters"];
export type HudSample = S["HudSample"];
export type MemoryEntry = S["MemoryEntry"];
export type MemoryBatch = S["MemoryBatch"];
export type MemoryCommit = S["Commit"];
export type Source = S["Source"];
export type IndexProgress = S["IndexProgress"];
export type RetrievalStatus = S["RetrievalStatus"];
export type OpenedChunk = S["OpenedChunk"];
export type SearchStatus = S["SearchStatus"];
export type ResearchReport = S["ResearchReport"];
