// One Council run, streamed. Answers arrive interleaved and are keyed by their blind label.
import { create } from "zustand";
import { parseFrames } from "../api/stream";
import type {
  AgreementCell,
  CouncilAnswer,
  CouncilEvent,
  CouncilMember,
  CouncilVerdict,
} from "../api/types";

interface CouncilState {
  running: boolean;
  mode: string;
  detail: string;
  members: CouncilMember[];
  streaming: Record<string, string>;
  answers: Record<string, CouncilAnswer>;
  agreement: AgreementCell[];
  agreementDetail: string;
  verdict: CouncilVerdict | null;
  error: string;

  run: (question: string, modelIds: string[], category: string) => Promise<void>;
  reset: () => void;
}

const EMPTY = {
  mode: "",
  detail: "",
  members: [] as CouncilMember[],
  streaming: {} as Record<string, string>,
  answers: {} as Record<string, CouncilAnswer>,
  agreement: [] as AgreementCell[],
  agreementDetail: "",
  verdict: null,
  error: "",
};

export const useCouncil = create<CouncilState>((set, get) => ({
  running: false,
  ...EMPTY,

  reset: () => set({ ...EMPTY, running: false }),

  run: async (question, modelIds, category) => {
    if (get().running || !question.trim()) return;
    set({ ...EMPTY, running: true });

    let response: Response;
    try {
      response = await fetch("/api/council/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, model_ids: modelIds, category }),
      });
    } catch (cause) {
      set({ running: false, error: String(cause) });
      return;
    }
    if (!response.ok || !response.body) {
      set({ running: false, error: `${response.status} ${response.statusText}` });
      return;
    }

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += value;
        const { frames, rest } = parseFrames(buffer);
        buffer = rest;
        for (const frame of frames) apply(set, JSON.parse(frame.data) as CouncilEvent);
      }
    } finally {
      set({ running: false });
    }
  },
}));

type Setter = (partial: Partial<CouncilState> | ((s: CouncilState) => Partial<CouncilState>)) => void;

function apply(set: Setter, event: CouncilEvent): void {
  switch (event.type) {
    case "plan":
      set({ members: event.members, mode: event.mode, detail: event.detail });
      break;
    case "answer_token":
      set((s) => ({
        streaming: { ...s.streaming, [event.label]: (s.streaming[event.label] ?? "") + event.text },
      }));
      break;
    case "answer_done":
      set((s) => ({ answers: { ...s.answers, [event.answer.label]: event.answer } }));
      break;
    case "agreement":
      set({ agreement: event.cells, agreementDetail: event.detail });
      break;
    case "verdict":
      set({ verdict: event.verdict });
      break;
    default:
      break;
  }
}
