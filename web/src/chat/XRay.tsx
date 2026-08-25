// Token x-ray (BRIEF.md 4.3): each token tinted by how sure the model was, and clickable so you
// can take a different branch of its own distribution.
//
// Confident reads cool, uncertain reads warm. Hallucination and recall genuinely look different,
// which is the whole point of showing it rather than describing it.
import { useMemo, useState } from "react";
import type { MessageTokens, TokenView } from "../api/types";
import TokenPopover from "./TokenPopover";

/** Token byte offsets are UTF-8; a JS string is UTF-16, so slice the encoded bytes. */
function sliceByBytes(content: string): (token: TokenView) => string {
  const bytes = new TextEncoder().encode(content);
  const decoder = new TextDecoder();
  return (token) => decoder.decode(bytes.slice(token.byte_start, token.byte_end));
}

function tint(logprob: number | null | undefined): string {
  if (logprob === null || logprob === undefined) return "transparent";
  const p = Math.exp(logprob);
  // 205° (cool, certain) → 28° (warm, uncertain). Alpha rises as certainty falls, so a confident
  // passage stays legible and an unsure one is impossible to miss.
  const hue = 28 + (205 - 28) * p;
  const alpha = 0.34 * (1 - p) + 0.05;
  return `hsl(${hue.toFixed(0)} 85% 55% / ${alpha.toFixed(3)})`;
}

export default function XRay({
  data,
  content,
  onForce,
}: {
  data: MessageTokens;
  content: string;
  onForce: (tokenIdx: number, token: string) => void;
}) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const slice = useMemo(() => sliceByBytes(content), [content]);

  // A continued message carries a prefix that predates the token log; render it plainly.
  const firstStart = data.tokens[0]?.byte_start ?? 0;
  const head = useMemo(
    () => new TextDecoder().decode(new TextEncoder().encode(content).slice(0, firstStart)),
    [content, firstStart],
  );
  const nudgeAt = useMemo(
    () => new Map(data.nudges.map((n) => [n.token_idx, n.text])),
    [data.nudges],
  );

  return (
    <p className="relative whitespace-pre-wrap leading-relaxed">
      {head && <span className="opacity-80">{head}</span>}
      {data.tokens.map((token) => (
        <span key={token.idx} className="relative">
          {nudgeAt.has(token.idx) && (
            <span
              className="mx-0.5 rounded bg-amber-400/25 px-1 text-[10px] uppercase tracking-wide text-amber-100"
              title={nudgeAt.get(token.idx)}
            >
              nudge
            </span>
          )}
          <button
            onClick={() => setOpenIdx(openIdx === token.idx ? null : token.idx)}
            style={{ background: tint(token.logprob) }}
            className="rounded-[3px] text-left hover:outline hover:outline-1 hover:outline-white/40"
            title={
              token.logprob == null
                ? undefined
                : `p=${Math.exp(token.logprob).toFixed(3)} — click for alternatives`
            }
          >
            {slice(token)}
          </button>
          {openIdx === token.idx && (
            <TokenPopover
              token={token}
              onPick={(alt) => {
                setOpenIdx(null);
                onForce(token.idx, alt);
              }}
              onClose={() => setOpenIdx(null)}
            />
          )}
        </span>
      ))}
    </p>
  );
}
