import { motion } from "framer-motion";
import type { Message as MessageModel } from "../api/types";
import { useState } from "react";
import { useGraph } from "../store/graph";
import { useSession } from "../store/session";
import { useXray } from "../store/xray";
import { messageVariants } from "../ui/motion";
import EditMessage from "./EditMessage";
import MessageActions from "./MessageActions";
import ReplayDiff from "./ReplayDiff";
import SiblingNav from "./SiblingNav";
import StreamingText from "./StreamingText";
import XRay from "./XRay";

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
  const running = useSession((s) => s.runId) !== null;
  const messages = useSession((s) => s.messages);
  const xrayOn = useXray((s) => s.enabled[message.id]) ?? false;
  const xrayData = useXray((s) => s.data[message.id]);
  const force = useXray((s) => s.force);
  const [showDiff, setShowDiff] = useState(false);

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
        {xrayOn && xrayData?.mean_logprob != null && (
          <span
            className="normal-case text-sky-200/70"
            title="Mean log-probability. A confidence figure, not an accuracy one."
          >
            · confidence {Math.exp(xrayData.mean_logprob).toFixed(2)}
          </span>
        )}
        {!streaming && !running && (
          <MessageActions
            message={message}
            showDiff={showDiff}
            onToggleDiff={() => setShowDiff(!showDiff)}
          />
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
      ) : xrayOn && xrayData && xrayData.supports_logprobs ? (
        <XRay
          data={xrayData}
          content={message.content}
          onForce={(idx, token) => void force(message.id, idx, token)}
        />
      ) : (
        <p className="whitespace-pre-wrap">{text}</p>
      )}

      {xrayOn && xrayData && !xrayData.supports_logprobs && (
        <p className="mt-2 text-[11px] text-ink-faint">
          This backend reported no per-token probabilities for this message, so there is nothing
          to x-ray. Nothing is being estimated in their place.
        </p>
      )}

      {showDiff && (
        <div className="mt-3">
          <ReplayDiff
            message={message}
            original={messages.find((m) => m.id === message.edited_from_id)}
          />
        </div>
      )}

      {streaming && text === "" && (
        <span className="text-ink-faint">waiting for the first token…</span>
      )}
    </motion.article>
  );
}
