import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { api } from "../api";
import type { PromptRow, PromptsResponse, RunOverview, SystemStatus } from "../types";
import { QuadrantChip, ScoreChip } from "../components/ui";
import { PromptRowDetail } from "../components/prompts/PromptRowDetail";
import { SelectionActions } from "../components/prompts/SelectionActions";
import { useSubmitJob } from "../hooks/useSubmitJob";

const FILTERS = [
  { value: "", label: "all" },
  { value: "errors", label: "errors" },
  { value: "undetermined", label: "undetermined" },
  { value: "cpv", label: "content-policy" },
  { value: "disagreement", label: "judge disagreement" },
];

const QUADRANT_FILTERS = ["", "breach", "scarecrow", "guarded", "fizzle"];

export function PromptsTable() {
  const { runName } = useParams<{ runName: string }>();

  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [quadrant, setQuadrant] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [rescoreModels, setRescoreModels] = useState<Set<string>>(new Set(["asr_claude", "strict_claude"]));
  const [attackTier, setAttackTier] = useState("");

  const overview = useQuery({
    queryKey: ["run", runName],
    queryFn: () => api.get<RunOverview>(`/runs/${runName}`),
  });
  const system = useQuery({
    queryKey: ["system"],
    queryFn: () => api.get<SystemStatus>("/system"),
  });

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (filter) params.set("filter", filter);
  if (quadrant) params.set("quadrant", quadrant);

  const prompts = useQuery({
    queryKey: ["prompts", runName, params.toString()],
    queryFn: () => api.get<PromptsResponse>(`/runs/${runName}/prompts?${params}`),
    refetchInterval: 15_000,
  });

  const submitJob = useSubmitJob([["prompts"]]);

  const rows = prompts.data?.rows ?? [];
  const scorers = prompts.data?.scorers ?? [];
  const allSelected = rows.length > 0 && selected.size === rows.length;

  const selectedRows = useMemo(
    () => rows.filter((r) => selected.has(r.conversation_id)),
    [rows, selected],
  );

  const runTier = overview.data?.meta.tier ?? "";
  const quadrantJudge = scorers.find((s) => s.startsWith("strict_")) ?? "";

  function toggle(cid: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  }

  function toggleRescoreModel(m: string) {
    setRescoreModels((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m);
      else next.add(m);
      return next;
    });
  }

  function reattack(tier: string) {
    if (
      !confirm(
        `Re-attack ${selected.size} prompt(s) on ${tier}? ` +
          "Existing responses for these objectives will be replaced (backups kept), and their scores invalidated.",
      )
    ) {
      return;
    }
    submitJob.mutate({
      kind: "attack",
      params: {
        tier,
        dataset_size: selectedRows.length,
        run_name: runName,
        objectives: selectedRows.map((r) => r.objective),
      },
    });
  }

  return (
    <div>
      {/* filters */}
      <div className="flex flex-wrap gap-2 mb-3">
        <input
          placeholder="search objective / response…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-72"
        />
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        <select value={quadrant} onChange={(e) => setQuadrant(e.target.value)}>
          {QUADRANT_FILTERS.map((qq) => (
            <option key={qq} value={qq}>{qq || "any quadrant"}</option>
          ))}
        </select>
        <span className="ml-auto text-xs text-zinc-500 self-center">
          {prompts.data ? `${prompts.data.count} / ${overview.data?.raw_count ?? "?"} prompts` : ""}
        </span>
      </div>

      {/* selection actions */}
      {selected.size > 0 && (
        <SelectionActions
          selectedCount={selected.size}
          scorers={scorers}
          rescoreModels={rescoreModels}
          onToggleRescoreModel={toggleRescoreModel}
          attackTier={attackTier}
          onAttackTierChange={setAttackTier}
          tiers={system.data?.tiers ?? []}
          runTier={runTier}
          objectives={selectedRows.map((r) => r.objective)}
          onRescore={(models) =>
            submitJob.mutate({
              kind: "rescore",
              params: { run_name: runName, models, conversation_ids: [...selected] },
            })
          }
          onReattack={reattack}
          onClear={() => setSelected(new Set())}
          error={submitJob.isError ? submitJob.error : null}
        />
      )}

      {/* table */}
      <div className="overflow-auto rounded-lg border border-zinc-800 max-h-[70vh]">
        <table className="data">
          <thead className="sticky top-0 bg-zinc-900 z-10">
            <tr>
              <th className="w-8">
                <input
                  type="checkbox"
                  className="accent-sky-500"
                  checked={allSelected}
                  onChange={() =>
                    setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.conversation_id)))
                  }
                />
              </th>
              <th>Objective</th>
              <th>Strat</th>
              <th>Turns</th>
              <th>PyRIT</th>
              {scorers.map((s) => (
                <th key={s} title={s}>{s}</th>
              ))}
              {quadrantJudge && <th title={quadrantJudge}>Quadrant</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <PromptTableRow
                key={r.conversation_id}
                row={r}
                scorers={scorers}
                quadrantJudge={quadrantJudge}
                selected={selected.has(r.conversation_id)}
                expanded={expanded === r.conversation_id}
                onToggle={() => toggle(r.conversation_id)}
                onExpand={() => setExpanded(expanded === r.conversation_id ? null : r.conversation_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PromptTableRow({
  row,
  scorers,
  quadrantJudge,
  selected,
  expanded,
  onToggle,
  onExpand,
}: {
  row: PromptRow;
  scorers: string[];
  quadrantJudge: string;
  selected: boolean;
  expanded: boolean;
  onToggle: () => void;
  onExpand: () => void;
}) {
  return (
    <>
      <tr className={selected ? "bg-sky-950/40" : undefined}>
        <td>
          <input type="checkbox" className="accent-sky-500" checked={selected} onChange={onToggle} />
        </td>
        <td className="max-w-md">
          <button onClick={onExpand} className="text-left text-xs hover:text-sky-400">
            {row.objective.length > 90 ? row.objective.slice(0, 90) + "…" : row.objective}
          </button>
        </td>
        <td className="text-xs text-zinc-500">{row.strategy}</td>
        <td className="font-mono text-xs">{row.executed_turns}</td>
        <td>
          <ScoreChip value={row.pyrit_outcome === "success" ? "true" : row.pyrit_outcome === "failure" ? "false" : row.pyrit_outcome} />
        </td>
        {scorers.map((s) => {
          const sc = row.scores[s];
          return (
            <td key={s}>
              {sc ? <ScoreChip value={sc.value} title={`${s}: ${sc.value}\n${sc.rationale.slice(0, 300)}`} /> : <span className="text-zinc-700">·</span>}
            </td>
          );
        })}
        {quadrantJudge && (
          <td>
            <QuadrantChip q={row.quadrants[quadrantJudge] ?? null} />
          </td>
        )}
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6 + scorers.length + (quadrantJudge ? 1 : 0)} className="bg-zinc-950">
            <PromptRowDetail row={row} scorers={scorers} />
          </td>
        </tr>
      )}
    </>
  );
}
