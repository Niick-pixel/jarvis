import { motion } from "framer-motion";
import type { Message as MessageModel } from "../api/types";
import { messageVariants } from "../ui/motion";
import StreamingText from "./StreamingText";

interface Props {
  message: MessageModel;
  /** Live text for the message currently being generated; the row is written before tokens. */
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
  const stopped = message.status === "stopped";
  const failed = message.status === "error";

  return (
    <motion.article
      variants={messageVariants}
      className={`max-w-[46rem] rounded-2xl border px-4 py-3 leading-relaxed ${ROLE_STYLES[message.role] ?? ""}`}
    >
      <header className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wide text-ink-faint">
        <span>{message.role}</span>
        {message.model_id && <span className="normal-case">· {message.model_id}</span>}
        {stopped && <span className="normal-case text-amber-300/80">· stopped, partial kept</span>}
        {failed && <span className="normal-case text-rose-300/80">· failed mid-answer</span>}
      </header>
      {streaming ? <StreamingText text={text} /> : <p className="whitespace-pre-wrap">{text}</p>}
      {streaming && text === "" && (
        <span className="text-ink-faint">waiting for the first token…</span>
      )}
    </motion.article>
  );
}
