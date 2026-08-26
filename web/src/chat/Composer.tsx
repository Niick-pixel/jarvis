import { useEffect, useRef, useState } from "react";
import { useSession } from "../store/session";
import { useVoice } from "../store/voice";
import Orb from "../scene/Orb";
import VoiceButton from "../voice/VoiceButton";
import Button from "../ui/Button";
import Sparkle from "../ui/Sparkle";

export default function Composer() {
  const [draft, setDraft] = useState("");
  const send = useSession((s) => s.send);
  const stop = useSession((s) => s.stop);
  const runId = useSession((s) => s.runId);
  const research = useSession((s) => s.research);
  const setResearch = useSession((s) => s.setResearch);
  const area = useRef<HTMLTextAreaElement>(null);
  const running = runId !== null;
  const phase = useVoice((s) => s.phase);
  const dictated = useVoice((s) => s.dictated);
  const consume = useVoice((s) => s.consume);
  const cancelListening = useVoice((s) => s.cancel);
  // The orb owns the slot whenever something is actually driving it (section 5.3); the sparkle
  // keeps it the rest of the time.
  const orbActive = phase !== "idle" || running;

  useEffect(() => {
    // Dictation lands in the box, not in the conversation: you get to read it before it is sent.
    if (!dictated) return;
    setDraft((current) => (current ? `${current.trimEnd()} ${dictated}` : dictated));
    consume();
    area.current?.focus();
  }, [dictated, consume]);

  useEffect(() => {
    // Esc stops and keeps, from anywhere. Never lose 900 tokens to a wrong turn at token 40.
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (phase === "listening") cancelListening();
      else if (runId) void stop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [runId, stop, phase, cancelListening]);

  const submit = () => {
    const content = draft.trim();
    if (!content || running) return;
    setDraft("");
    void send(content);
  };

  return (
    <div className="mx-auto w-full max-w-4xl px-6 pb-6">
      <div className="glass flex items-end gap-2 rounded-2xl p-2">
        <span className="flex h-10 w-8 items-center justify-center">
          {orbActive ? <Orb /> : <Sparkle />}
        </span>
        <textarea
          ref={area}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={
            phase === "listening"
              ? "Listening - Esc cancels"
              : phase === "transcribing"
                ? "Working out what you said"
                : running
                  ? "Generating - Esc stops and keeps the partial"
                  : "Say something"
          }
          className="max-h-48 min-h-[2.5rem] flex-1 resize-none bg-transparent px-3 py-2 text-ink outline-none placeholder:text-ink-faint"
        />
        <VoiceButton />
        <Button
          onClick={() => setResearch(!research)}
          variant={research ? "primary" : "ghost"}
          title="Search the web first, in rounds, and cite what comes back. Requires a local SearXNG."
        >
          Research
        </Button>
        {running ? (
          <Button variant="primary" onClick={() => void stop()} title="Esc">
            Stop
          </Button>
        ) : (
          <Button variant="primary" onClick={submit} disabled={draft.trim() === ""}>
            Send
          </Button>
        )}
      </div>
    </div>
  );
}
