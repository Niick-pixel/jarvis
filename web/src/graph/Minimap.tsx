// The conversation as it actually is: a tree. Click any node to read that branch.
import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { useGraph } from "../store/graph";
import { useSession } from "../store/session";
import Button from "../ui/Button";
import { SPRING } from "../ui/motion";
import { layout } from "./layout";

const ROLE_FILL: Record<string, string> = {
  user: "#8ec5ff",
  assistant: "#b79dff",
  system: "#7f8aa3",
  tool: "#ffc46b",
};

export default function Minimap() {
  const messages = useSession((s) => s.messages);
  const activePath = useSession((s) => s.activePath);
  const switchTo = useGraph((s) => s.switchTo);
  const [open, setOpen] = useState(false);

  const model = useMemo(() => layout(messages, activePath), [messages, activePath]);
  const branches = model.nodes.length - activePath.length;

  return (
    <div className="pointer-events-auto absolute right-4 top-4 z-20 flex flex-col items-end gap-2">
      <Button
        onClick={() => setOpen(!open)}
        variant={open ? "primary" : "ghost"}
        title="The conversation is a tree, not a scroll"
      >
        Tree {branches > 0 && <span className="text-ink-faint">+{branches}</span>}
      </Button>

      <AnimatePresence>
        {open && model.nodes.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -6 }}
            transition={SPRING}
            className="glass max-h-[60vh] overflow-auto rounded-2xl p-3"
          >
            <svg
              width={model.width + 32}
              height={model.height + 32}
              viewBox={`-16 -16 ${model.width + 32} ${model.height + 32}`}
              className="overflow-visible"
            >
              {model.links.map((link, index) => (
                <line
                  key={index}
                  x1={link.from.x}
                  y1={link.from.y}
                  x2={link.to.x}
                  y2={link.to.y}
                  stroke={link.onPath ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.14)"}
                  strokeWidth={link.onPath ? 1.8 : 1}
                />
              ))}
              {model.nodes.map((node) => (
                <g
                  key={node.id}
                  transform={`translate(${node.x},${node.y})`}
                  onClick={() => void switchTo(node.id)}
                  className="cursor-pointer"
                >
                  <title>{node.label}</title>
                  <circle
                    r={node.onPath ? 6 : 4.5}
                    fill={ROLE_FILL[node.role] ?? "#8892a6"}
                    opacity={node.onPath ? 1 : 0.45}
                    stroke={node.onPath ? "rgba(255,255,255,0.9)" : "none"}
                    strokeWidth={1.5}
                  />
                  {node.forked && (
                    <circle r={9} fill="none" stroke="rgba(255,196,107,0.6)" strokeWidth={1} />
                  )}
                </g>
              ))}
            </svg>
            <p className="mt-2 max-w-[16rem] text-[10px] leading-snug text-ink-faint">
              {model.nodes.length} nodes, {activePath.length} on the branch you are reading. A ring
              marks a fork. Nothing here is ever deleted by editing.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
