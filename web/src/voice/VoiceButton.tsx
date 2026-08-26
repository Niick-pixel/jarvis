// The mic. It is never a dead button: when speech is unavailable, pressing it says why in a
// sentence and prints the command that fixes it, rather than sitting there greyed out.
import Button from "../ui/Button";
import { useVoice } from "../store/voice";

const LABEL = {
  idle: "Speak",
  listening: "Stop",
  transcribing: "Hearing",
  speaking: "Speak",
} as const;

export default function VoiceButton() {
  const status = useVoice((s) => s.status);
  const phase = useVoice((s) => s.phase);
  const listen = useVoice((s) => s.listen);
  const finish = useVoice((s) => s.finish);
  const ready = status?.stt.available ?? false;
  const engine = status?.stt;

  const press = () => {
    if (!ready) {
      useVoice.setState({
        error: engine ? `${engine.reason} Fix: ${engine.fix}` : "Voice status is still loading.",
      });
      return;
    }
    if (phase === "listening") void finish();
    else if (phase === "idle") void listen();
  };

  const cost = engine?.vram_estimate_mb ? ` ~${engine.vram_estimate_mb}MB VRAM` : "";
  const title = ready
    ? `${engine?.engine} ${engine?.model_id} on ${engine?.device}.${cost} Esc cancels.`
    : (engine?.reason ?? "Checking what this machine can do");

  return (
    <Button
      onClick={press}
      variant={phase === "listening" ? "primary" : "ghost"}
      title={title}
      disabled={phase === "transcribing"}
    >
      {LABEL[phase]}
    </Button>
  );
}
