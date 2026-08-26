// Pairwise agreement, as a sequential heatmap.
//
// One hue, monotonic in similarity - never a rainbow, because the quantity is magnitude and a
// rainbow implies categories. Cell numbers wear ink tokens rather than the cell colour, and the
// whole thing is a real <table> with header cells, so the accessible view *is* the chart rather
// than a second rendering of it.
import type { AgreementCell } from "../api/types";

const HUE = 190;

/** Cosine runs -1..1. The colour scale covers 0..1 and clamps below that; the printed number is
 *  never clamped, because the cell should show what was measured, not what the scale can paint. */
function shade(similarity: number): string {
  const value = Math.max(0, Math.min(1, similarity));
  return `hsl(${HUE} 70% 52% / ${(0.06 + 0.5 * value).toFixed(3)})`;
}

export default function AgreementMatrix({
  cells,
  labels,
  detail,
}: {
  cells: AgreementCell[];
  labels: string[];
  detail: string;
}) {
  if (labels.length < 2) return null;
  const lookup = new Map<string, number>();
  for (const cell of cells) {
    lookup.set(`${cell.a}|${cell.b}`, cell.similarity);
    lookup.set(`${cell.b}|${cell.a}`, cell.similarity);
  }

  return (
    <figure className="m-0">
      <figcaption className="mb-2 text-[11px] text-ink-faint">
        Agreement between answers · {detail}
      </figcaption>
      <table className="border-separate border-spacing-[2px] text-[11px]">
        <thead>
          <tr>
            <th className="w-6" aria-label="answer" />
            {labels.map((label) => (
              <th key={label} scope="col" className="w-10 pb-1 font-mono text-ink-faint">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((row) => (
            <tr key={row}>
              <th scope="row" className="pr-1 text-right font-mono text-ink-faint">
                {row}
              </th>
              {labels.map((column) => {
                const self = row === column;
                const value = self ? 1 : (lookup.get(`${row}|${column}`) ?? 0);
                return (
                  <td
                    key={column}
                    title={
                      self
                        ? `${row} compared with itself`
                        : `${row} vs ${column}: cosine similarity ${value.toFixed(3)}`
                    }
                    style={{ background: self ? "transparent" : shade(value) }}
                    className={`h-9 w-10 rounded text-center font-mono ${
                      self ? "text-ink-faint" : "text-ink"
                    }`}
                  >
                    {self ? "—" : value.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 max-w-sm text-[10px] leading-snug text-ink-faint">
        Cosine similarity of the answers' embeddings. Values run −1 to 1; the colour scale covers 0
        to 1 and anything below reads as the palest cell, but the number is what was measured.
        Close agreement is weak evidence — models share training data and failure modes. A split is
        the interesting case.
      </p>
    </figure>
  );
}
