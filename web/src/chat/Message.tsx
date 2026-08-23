import { motion } from "framer-motion";
import type { Message as MessageModel } from "../api/types";
import { useGraph } from "../store/graph";
import { useSession } from "../store/session";
import { messageVariants } from "../ui/motion";
import EditMessage from "./EditMessage";
import SiblingNav from "./SiblingNav";
import StreamingText from "./StreamingText";

interface Props {
  message: MessageModel;
  liveText?: string;
  streaming?: boolean;
}

const ROLE_STYLES: Record<string, string> = {
  user: "ml-auto bg-white/10 border-white/12",
  assistant: "mr-auto glass",
  system: "mr-auto bg-transparent border-white/8 text-ink-muted",
  tool: "mr-auto bg-transparent border-white/8 text-ink-muted font-mono text-sm",
};

export default function Message({ message, liveText, streaming }: Props) {
  const text = streaming ? (liveText ?? "") : message.content;
  const editing = useGraph((s) => s.editing) === message.id;
  const beginEdit = useGraph((s) => s.beginEdit);
  const continueFrom = useSession((s) => s.continueFrom);
  const running = useSession((s) => s.runId) !== null;

  const stopped = message.status === "stopped";
  const failed = message.status === "error";
  const forked = message.forked_reason;

  return (
    <motion.article
      variants={messageVariants}
      className={`group max-w-[46rem] rounded-2xl border px-4 py-3 leading-relaxed ${ROLE_STYLES[message.role] ?? ""}`}
    >
      <header className="mb-1 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-ink-faint">
        <span>{message.role}</span>
        {message.model_id && <span className="normal-case">· {message.model_id}</span>}
        {stopped && <span className="normal-case text-amber-300/80">· stopped, partial kept</span>}
        {failed && <span className="normal-case text-rose-300/80">· failed mid-answer</span>}
        {forked && <span className="normal-case text-sky-300/70">· {forked}</span>}
        <SiblingNav messageId={message.id} />
        {!streaming && !running && (
          <span className="ml-auto flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={() => beginEdit(message.id)}
              className="rounded-lg px-2 py-0.5 normal-case hover:bg-white/10 hover:text-ink"
              title="Edit this message — saving forks a new branch"
            >
              edit
            </button>
            {message.role === "assistant" && (
              <button
                onClick={() => void continueFrom(message.id)}
                className="rounded-lg px-2 py-0.5 normal-case hover:bg-white/10 hover:text-ink"
                title="Let the model carry on from this text"
              >
                continue
              </button>
            )}
          </span>
        )}
      </header>

      {editing ? (
        <EditMessage
          messageId={message.id}
          initial={message.content}
          isAssistant={message.role === "assistant"}
        />
      ) : streaming ? (
        <StreamingText text={text} />
      ) : (
        <p className="whitespace-pre-wrap">{text}</p>
      )}

      {streaming && text === "" && (
        <span className="text-ink-faint">waiting for the first token…</span>
      )}
    </motion.article>
  );
}
