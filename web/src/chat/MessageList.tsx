import { motion } from "framer-motion";
import { useEffect, useRef } from "react";
import { useSession } from "../store/session";
import { listVariants } from "../ui/motion";
import Message from "./Message";

export default function MessageList() {
  const messages = useSession((s) => s.messages);
  const activePath = useSession((s) => s.activePath);
  const streamingId = useSession((s) => s.streamingId);
  const streamingText = useSession((s) => s.streamingText);
  const bottom = useRef<HTMLDivElement>(null);

  // Only the active branch is shown. The other branches still exist; M2 adds the switcher.
  const onPath = new Set(activePath);
  const visible = messages.filter((m) => onPath.has(m.id) || m.id === streamingId);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [visible.length, streamingText]);

  return (
    <motion.div
      variants={listVariants}
      initial="hidden"
      animate="visible"
      className="scroll-thin mx-auto flex w-full max-w-4xl flex-col gap-4 overflow-y-auto px-6 py-8"
    >
      {visible.length === 0 && (
        <p className="mt-24 text-center text-ink-faint">
          Nothing here yet. Everything you type stays on this machine.
        </p>
      )}
      {visible.map((message) => (
        <Message
          key={message.id}
          message={message}
          liveText={streamingText}
          streaming={message.id === streamingId}
        />
      ))}
      <div ref={bottom} />
    </motion.div>
  );
}
