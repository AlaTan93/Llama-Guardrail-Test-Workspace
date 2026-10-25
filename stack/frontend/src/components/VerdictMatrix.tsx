import { kindLabel } from "../lib/format";
import type { Score } from "../types";

/** The 6-cell verdict matrix: one (ASR, REF) pair per judge for one objective.
 * T = true, F = false, ? = undetermined. Hover shows the judge's rationale. */
export function VerdictMatrix({ scores }: { scores: Score[] }) {
  if (!scores.length) return <span className="text-zinc-500">no scores</span>;

  const cells = [...scores]
    .sort((a, b) => a.judge_alias.localeCompare(b.judge_alias) || a.scorer_kind.localeCompare(b.scorer_kind))
    .map((s, i) => {
      const undetermined = s.status !== "complete";
      const verdict = undetermined ? "?" : s.value_bool ? "T" : "F";
      const tone = undetermined
        ? "border-amber-500/50 text-amber-400"
        : s.value_bool
          ? "border-emerald-500/50"
          : "border-red-500/40";
      return (
        <span
          key={i}
          title={s.rationale || ""}
          className={`inline-flex flex-col items-center rounded-md border px-1.5 py-0.5 font-mono text-[11px] leading-tight ${tone}`}
        >
          <span className="text-[9px] text-zinc-500">{s.judge_alias.replace("judge-", "")}</span>
          <span>{verdict}</span>
          <span className="text-[8px] tracking-wide text-zinc-500">{kindLabel(s.scorer_kind)}</span>
        </span>
      );
    });

  return <div className="flex flex-wrap gap-1.5">{cells}</div>;
}
