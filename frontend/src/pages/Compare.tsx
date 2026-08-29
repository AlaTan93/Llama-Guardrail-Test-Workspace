import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { ComparePromptsResponse, CompareResponse, RunSummary } from "../types";
import { Panel, ScoreChip, SummaryTable, TierBadge } from "../components/ui";

const KINDS = [
  { value: "asr", label: "ASR" },
  { value: "refusal", label: "Refusal" },
  { value: "crosstab", label: "Crosstab" },
];

export function Compare() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<{ runs: RunSummary[] }>("/runs"),
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [kind, setKind] = useState("asr");
  const [showPrompts, setShowPrompts] = useState(false);

  const list = runs.data?.runs ?? [];
  const runsParam = [...selected].join(",");

  const compare = useQuery({
    queryKey: ["compare", runsParam, kind],
    queryFn: () => api.get<CompareResponse>(`/compare?kind=${kind}&runs=${encodeURIComponent(runsParam)}`),
    enabled: selected.size >= 2,
  });

  const comparePrompts = useQuery({
    queryKey: ["comparePrompts", runsParam],
    queryFn: () => api.get<ComparePromptsResponse>(`/compare/prompts?runs=${encodeURIComponent(runsParam)}`),
    enabled: showPrompts && selected.size >= 2,
  });

  function toggle(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  const tierOrder = (t: string) => {
    const idx = ["Q2_K", "Q3_K_S", "Q3_K_M", "Q3_K_L", "IQ4_XS", "Q4_K_S", "Q4_K_M", "Q5_K_S", "Q5_K_M", "Q6_K", "Q8_0", "BF16"].indexOf(t);
    return idx === -1 ? 99 : idx;
  };
  const sortedCols = [...(compare.data?.columns ?? [])].sort((a, b) => tierOrder(a.tier) - tierOrder(b.tier));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Compare</h1>

      <Panel title={`Select runs (${selected.size} selected — pick at least 2)`}>
        <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3 max-h-64 overflow-auto">
          {list.map((r) => (
            <label key={r.name} className="text-xs flex items-center gap-2 cursor-pointer">
              <input type="checkbox" className="accent-sky-500" checked={selected.has(r.name)} onChange={() => toggle(r.name)} />
              <span className="font-mono truncate">{r.name}</span>
              <TierBadge tier={r.tier} />
            </label>
          ))}
        </div>
      </Panel>

      {selected.size >= 2 && (
        <>
          <div className="flex gap-2 mb-4">
            {KINDS.map((k) => (
              <button
                key={k.value}
                onClick={() => setKind(k.value)}
                className={kind === k.value && !showPrompts ? "bg-sky-600 hover:bg-sky-500" : "bg-zinc-800 hover:bg-zinc-700"}
              >
                {k.label}
              </button>
            ))}
            <button
              onClick={() => setShowPrompts((v) => !v)}
              className={showPrompts ? "bg-sky-600 hover:bg-sky-500" : "bg-zinc-800 hover:bg-zinc-700"}
            >
              Per-prompt
            </button>
          </div>

          {!showPrompts && compare.data && (
            <Panel title={`${KINDS.find((k) => k.value === kind)!.label} metrics across runs (columns sorted by tier)`}>
              <SummaryTable
                rows={compare.data.metrics.map((m) => {
                  const row: Record<string, string> = { metric: m.metric };
                  for (const col of sortedCols) {
                    for (const [key, v] of Object.entries(m.values)) {
                      if (key.startsWith(`${col.run}::`)) {
                        row[`${col.tier}\n${col.run.slice(-6)}`] = v === "" ? "—" : v;
                      }
                    }
                  }
                  return row;
                })}
              />
              <p className="text-xs text-zinc-500 mt-2">
                Columns are <code>tier + run suffix</code>; values are per-scorer metrics where available.
              </p>
            </Panel>
          )}

          {showPrompts && comparePrompts.data && (
            <Panel title={`Per-prompt verdicts across ${comparePrompts.data.runs.length} runs`}>
              <PerPromptDiff data={comparePrompts.data} />
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function PerPromptDiff({ data }: { data: ComparePromptsResponse }) {
  const [onlyDiff, setOnlyDiff] = useState(false);

  const rows = data.objectives.filter((o) => {
    if (!onlyDiff) return true;
    const asrVals: string[] = [];
    for (const entry of Object.values(o.runs)) {
      for (const [scorer, v] of Object.entries(entry.scores)) {
        if (scorer.startsWith("asr_")) asrVals.push(v);
      }
    }
    return new Set(asrVals).size > 1;
  });

  const runs = data.runs;

  return (
    <div>
      <label className="text-xs flex items-center gap-2 mb-2 cursor-pointer">
        <input type="checkbox" className="accent-sky-500" checked={onlyDiff} onChange={() => setOnlyDiff((v) => !v)} />
        only show prompts where ASR judges disagree
      </label>
      <div className="overflow-auto max-h-[60vh] rounded border border-zinc-800">
        <table className="data">
          <thead className="sticky top-0 bg-zinc-900">
            <tr>
              <th>Objective</th>
              {runs.map((r) => (
                <th key={r} className="font-mono text-xs">
                  {data.tiers[r]}<br />
                  <span className="text-zinc-500">{r.slice(-6)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.objective}>
                <td className="max-w-lg text-xs">
                  {o.objective.length > 100 ? o.objective.slice(0, 100) + "…" : o.objective}
                </td>
                {runs.map((r) => {
                  const entry = o.runs[r];
                  return (
                    <td key={r}>
                      {entry ? (
                        <div className="flex gap-1">
                          {Object.entries(entry.scores)
                            .filter(([s]) => s.startsWith("asr_") || s.startsWith("strict_"))
                            .map(([s, v]) => (
                              <span key={s} title={`${s}: ${v}`}>
                                <ScoreChip value={v} />
                              </span>
                            ))}
                        </div>
                      ) : (
                        <span className="text-zinc-700 text-xs">absent</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-zinc-500 mt-2">
        Chips: ASR verdict then strict refusal verdict per run (T=true F=false E=error U=undetermined CPV=content-policy).
      </p>
    </div>
  );
}
