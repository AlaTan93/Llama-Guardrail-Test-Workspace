import type { Objective } from "../types";

/** Expandable conversation transcript + raw judge rationales for one objective. */
export function Conversation({ objective }: { objective: Objective }) {
  if (!objective.turns?.length && !objective.scores?.length) return null;

  const transcript = (objective.turns ?? [])
    .map((t) => `— ${t.role} —\n${t.content}`)
    .join("\n\n");
  const rationales = (objective.scores ?? [])
    .map(
      (s) =>
        `[${s.scorer_kind} @ ${s.judge_alias}] ${s.status === "complete" ? s.value_bool : "undetermined"} — ${s.rationale ?? ""}`,
    )
    .join("\n");

  return (
    <details className="mt-1.5">
      <summary className="cursor-pointer text-[11px] text-zinc-500 hover:text-zinc-300">
        conversation &amp; rationales
      </summary>
      <pre className="mt-1.5 max-w-2xl overflow-x-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-zinc-950 p-2.5 text-xs">
        {transcript}
        {rationales ? `\n\n${rationales}` : ""}
      </pre>
    </details>
  );
}
