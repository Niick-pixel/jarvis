// Speech in and out. Every failure here becomes a sentence on screen: a disabled mic button with
// no explanation is exactly the thing this app is not.
import { create } from "zustand";
import { ApiError, api, speakStream } from "../api/client";
import type { VoiceStatus } from "../api/types";
import { drive } from "../voice/level";
import { MicError, type Recording, record } from "../voice/mic";
import { type Playback, play } from "../voice/player";
import { useSession } from "./session";

export type VoicePhase = "idle" | "listening" | "transcribing" | "speaking";

let recording: Recording | null = null;
let playback: Playback | null = null;

interface VoiceState {
  status: VoiceStatus | null;
  phase: VoicePhase;
  error: string | null;
  dictated: string;
  speakingId: string | null;

  refresh: () => Promise<void>;
  listen: () => Promise<void>;
  finish: () => Promise<void>;
  cancel: () => void;
  consume: () => void;
  speak: (messageId: string, text: string) => Promise<void>;
  hush: () => void;
  dismiss: () => void;
}

export const useVoice = create<VoiceState>((set, get) => ({
  status: null,
  phase: "idle",
  error: null,
  dictated: "",
  speakingId: null,

  refresh: async () => {
    set({ status: await api.voiceStatus() });
  },

  listen: async () => {
    if (get().phase !== "idle") return;
    try {
      recording = await record();
      set({ phase: "listening", error: null });
      useSession.getState().setVisual("listening");
    } catch (error) {
      recording = null;
      set({ error: error instanceof MicError ? error.message : String(error) });
    }
  },

  /** Stop recording and send the clip. The mic closes before the request, not after it. */
  finish: async () => {
    const active = recording;
    recording = null;
    if (!active) return;
    set({ phase: "transcribing" });
    useSession.getState().setVisual("idle");
    try {
      const clip = await active.stop();
      const transcript = await api.transcribe(clip);
      const text = transcript.text.trim();
      set({
        phase: "idle",
        dictated: text,
        error: text ? null : "Nothing was said in that clip.",
      });
    } catch (error) {
      set({ phase: "idle", error: message(error) });
      // The reason may have changed (the model was deleted, the extra uninstalled), so re-read it.
      void get().refresh().catch(() => undefined);
    }
  },

  cancel: () => {
    recording?.cancel();
    recording = null;
    drive.reset();
    set({ phase: "idle" });
    useSession.getState().setVisual("idle");
  },

  consume: () => set({ dictated: "" }),

  speak: async (messageId: string, text: string) => {
    get().hush();
    try {
      const body = await speakStream({ text, voice: null });
      playback = play(body);
      set({ phase: "speaking", speakingId: messageId, error: null });
      await playback.finished;
      if (get().speakingId === messageId) set({ phase: "idle", speakingId: null });
    } catch (error) {
      set({ phase: "idle", speakingId: null, error: message(error) });
      void get().refresh().catch(() => undefined);
    }
  },

  hush: () => {
    playback?.stop();
    playback = null;
    drive.reset();
    set((s) => (s.phase === "speaking" ? { phase: "idle", speakingId: null } : s));
  },

  dismiss: () => set({ error: null }),
}));

function message(error: unknown): string {
  if (error instanceof ApiError) return error.body.message;
  if (error instanceof Error) return error.message;
  return "Voice failed for a reason it did not name.";
}
