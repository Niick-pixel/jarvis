// The per-message instrument row: fork it, carry on from it, replay it, or look inside it.
import type { Message } from "../api/types";
import { useGraph } from "../store/graph";
import { useSession } from "../store/session";
import { useXray } from "../store/xray";

const BUTTON = "rounded-lg px-2 py-0.5 normal-case hover:bg-white/10 hover:text-ink";

export default function MessageActions({
  message,
  showDiff,
  onToggleDiff,
}: {
  message: Message;
  showDiff: boolean;
  onToggleDiff: () => void;
}) {
  const beginEdit = useGraph((s) => s.beginEdit);
  const continueFrom = useSession((s) => s.continueFrom);
  const rerun = useSession((s) => s.rerun);
  const toggleXray = useXray((s) => s.toggle);
  const xrayOn = useXray((s) => s.enabled[message.id]) ?? false;
  const assistant = message.role === "assistant";

  return (
    <span className="ml-auto flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        onClick={() => beginEdit(message.id)}
        className={BUTTON}
        title="Edit this message — saving forks a new branch"
      >
        edit
      </button>
      {assistant && (
        <>
          <button
            onClick={() => void continueFrom(message.id)}
            className={BUTTON}
            title="Let the model carry on from this text"
          >
            continue
          </button>
          <button
            onClick={() => void rerun(message.id)}
            className={BUTTON}
            title="Replay with the exact same seed and parameters"
          >
            rerun
          </button>
          <button
            onClick={() => void toggleXray(message.id)}
            className={`${BUTTON} ${xrayOn ? "bg-white/10 text-ink" : ""}`}
            title="Tint each token by how sure the model was, and click one to change it"
          >
            x-ray
          </button>
          {message.forked_reason === "rerun" && (
            <button
              onClick={onToggleDiff}
              className={`${BUTTON} ${showDiff ? "bg-white/10 text-ink" : ""}`}
              title="Word-level diff against the message this replayed"
            >
              diff
            </button>
          )}
        </>
      )}
    </span>
  );
}
