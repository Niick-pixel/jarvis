// Editing any message, including the assistant's own. Saving forks a sibling; the original stays
// exactly where it was. This is the one thing no hosted chat product will let you do.
import { useEffect, useRef, useState } from "react";
import { useGraph } from "../store/graph";
import { useSession } from "../store/session";
import Button from "../ui/Button";

export default function EditMessage({
  messageId,
  initial,
  isAssistant,
}: {
  messageId: string;
  initial: string;
  isAssistant: boolean;
}) {
  const [draft, setDraft] = useState(initial);
  const { saveEdit, cancelEdit } = useGraph();
  const continueFrom = useSession((s) => s.continueFrom);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    area.current?.focus();
    area.current?.setSelectionRange(draft.length, draft.length);
    // Focus once on open; re-focusing on every keystroke would fight the caret.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    await saveEdit(messageId, draft);
  };

  const saveAndContinue = async () => {
    const forkedId = await saveEdit(messageId, draft);
    if (forkedId) await continueFrom(forkedId);
  };

  return (
    <div className="flex flex-col gap-2">
      <textarea
        ref={area}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") cancelEdit();
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void save();
        }}
        rows={Math.min(16, draft.split("\n").length + 2)}
        className="w-full resize-y rounded-xl border border-white/15 bg-black/25 p-3 text-ink outline-none"
      />
      <div className="flex items-center gap-2 text-[11px] text-ink-faint">
        <Button variant="primary" onClick={() => void save()}>
          Save as new branch
        </Button>
        {isAssistant && (
          <Button
            onClick={() => void saveAndContinue()}
            title="Fork with your text, then let the model carry on from it"
          >
            Save and continue
          </Button>
        )}
        <Button onClick={cancelEdit}>Cancel</Button>
        <span className="ml-auto">The original is kept as a sibling — ⌘/Ctrl+Enter saves.</span>
      </div>
    </div>
  );
}
