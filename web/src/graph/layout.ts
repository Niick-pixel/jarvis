// Tree layout for the minimap. d3-hierarchy does the geometry; we own the rendering, because a
// conversation tree is small and bespoke SVG is easier to read than a chart library's output.
import { stratify, tree } from "d3-hierarchy";
import type { Message } from "../api/types";

const VIRTUAL_ROOT = "__root__";

export interface LaidOutNode {
  id: string;
  x: number;
  y: number;
  role: Message["role"];
  onPath: boolean;
  forked: Message["forked_reason"];
  label: string;
}

export interface LaidOutLink {
  from: { x: number; y: number };
  to: { x: number; y: number };
  onPath: boolean;
}

export interface Layout {
  nodes: LaidOutNode[];
  links: LaidOutLink[];
  width: number;
  height: number;
}

/** A conversation can have more than one root, so everything hangs off a virtual one. */
export function layout(
  messages: Message[],
  activePath: string[],
  nodeGap = 26,
  levelGap = 34,
): Layout {
  if (messages.length === 0) return { nodes: [], links: [], width: 0, height: 0 };

  const rows = [
    { id: VIRTUAL_ROOT, parent: "" },
    ...messages.map((m) => ({ id: m.id, parent: m.parent_id ?? VIRTUAL_ROOT })),
  ];
  const byId = new Map(messages.map((m) => [m.id, m]));
  const onPath = new Set(activePath);

  const root = stratify<{ id: string; parent: string }>()
    .id((d) => d.id)
    .parentId((d) => d.parent || null)(rows);

  const depth = root.height;
  const leaves = root.leaves().length;
  const width = Math.max(1, leaves) * nodeGap;
  const height = Math.max(1, depth) * levelGap;
  tree<{ id: string; parent: string }>().size([width, height])(root);

  const nodes: LaidOutNode[] = [];
  const links: LaidOutLink[] = [];

  root.each((node) => {
    if (node.data.id === VIRTUAL_ROOT) return;
    const message = byId.get(node.data.id);
    if (!message) return;
    const point = node as unknown as { x: number; y: number };
    nodes.push({
      id: message.id,
      x: point.x,
      y: point.y,
      role: message.role,
      onPath: onPath.has(message.id),
      forked: message.forked_reason,
      label: `${message.role}: ${message.content.slice(0, 60)}`,
    });
    const parent = node.parent as unknown as { x: number; y: number; data: { id: string } } | null;
    if (parent && parent.data.id !== VIRTUAL_ROOT) {
      links.push({
        from: { x: parent.x, y: parent.y },
        to: { x: point.x, y: point.y },
        onPath: onPath.has(message.id) && onPath.has(parent.data.id),
      });
    }
  });

  return { nodes, links, width, height };
}
