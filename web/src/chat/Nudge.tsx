// Live steering (BRIEF.md 4.4). This input stays enabled while the model is generating: send an
// interjection and the run stops, keeps what it wrote, and carries on from there with your note
// in context. You never lose 900 tokens because it went wrong at token 40.
import { useState } from "react";
import { api } from "../api/client";
import { useSession } from "../store/session";
import Button from "../ui/Button";

export default function Nudge() {
  const [text, setText] = useState("");
  const runId = useSession((s) => s.runId);
  const conversation = useSession((s) => s.conversation);
  const runStream = useSession((s) => s.runStream);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const note = text.trim();
    if (!note || !runId || !conversation || busy) return;
    setBusy(true);
    setText("");
    try {
      // Records where it landed and stops the run, leaving the partial settled on disk.
      const { message_id } = await api.nudge(runId, note);
      await runStream({
        conversation_id: conversation.id,
        continue_from: message_id,
        nudge: note,
      });
    } finally {
      setBusy(false);
    }
  };

  if (!runId) return null;

  return (
    <div className="mx-auto flex w-full max-w-4xl items-center gap-2 px-6 pb-2">
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") void submit();
        }}
        placeholder="Nudge it mid-answer — 'be shorter', 'you're wrong about X'…"
        className="flex-1 rounded-xl border border-amber-300/25 bg-amber-300/10 px-3 py-1.5 text-[13px] text-ink outline-none placeholder:text-amber-100/40"
      />
      <Button onClick={() => void submit()} disabled={busy || text.trim() === ""}>
        Nudge
      </Button>
    </div>
  );
}
