import { ScoreChip, QuadrantChip } from "../ui";
import type { PromptRow } from "../../types";

/** Expanded per-prompt detail: full response + every judge's rationale. */
export function PromptRowDetail({ row, scorers }: { row: PromptRow; scorers: string[] }) {
  return (
    <div className="grid gap-3 p-2 md:grid-cols-2">
      <div>
        <h4 className="text-xs font-semibold text-zinc-400 mb-1">Objective</h4>
        <p className="text-xs mb-3">{row.objective}</p>
        <h4 className="text-xs font-semibold text-zinc-400 mb-1">Victim response</h4>
        <pre className="text-xs whitespace-pre-wrap bg-black/40 rounded p-2 max-h-64 overflow-auto">{row.last_response || "(empty)"}</pre>
        <p className="text-[11px] text-zinc-500 mt-1">
          pyrit_outcome: {row.pyrit_outcome} — {row.pyrit_outcome_reason}
        </p>
      </div>
      <div>
        <h4 className="text-xs font-semibold text-zinc-400 mb-1">Judge rationales</h4>
        {scorers.map((s) => {
          const sc = row.scores[s];
          if (!sc) return null;
          return (
            <div key={s} className="mb-2">
              <div className="flex items-center gap-2">
                <ScoreChip value={sc.value} />
                <span className="text-xs font-mono text-zinc-300">{s}</span>
              </div>
              <p className="text-[11px] text-zinc-500 mt-0.5">{sc.rationale || "(no rationale)"}</p>
            </div>
          );
        })}
        {Object.entries(row.quadrants).map(([judge, quad]) => (
          <div key={judge} className="mt-2">
            <QuadrantChip q={quad} /> <span className="text-[11px] text-zinc-500 font-mono">{judge}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
