import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api";
import type { RunOverview } from "../types";
import { Panel, StatusBadge, SummaryTable, TierBadge } from "../components/ui";
import { PromptsTable } from "./PromptsTable";

type Tab = "overview" | "prompts" | "meta";

export function RunDetail() {
  const { runName } = useParams<{ runName: string }>();
  const [tab, setTab] = useState<Tab>("overview");

  const overview = useQuery({
    queryKey: ["run", runName],
    queryFn: () => api.get<RunOverview>(`/runs/${runName}`),
    refetchInterval: (q) => (q.state.data?.status === "complete" ? false : 10_000),
  });

  if (overview.isLoading) return <p className="text-zinc-500">Loading…</p>;
  if (overview.error) return <p className="text-red-400">{String(overview.error)}</p>;

  const d = overview.data!;

  return (
    <div>
      <div className="flex items-center gap-3 mb-1 flex-wrap">
        <Link to="/" className="text-zinc-500 hover:text-zinc-300 text-sm">← Runs</Link>
        <h1 className="text-xl font-mono">{runName}</h1>
        {d.meta.victim && "model" in d.meta.victim && d.meta.victim.model && (
          <span className="px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-200" title={d.meta.victim.model}>
            {d.meta.victim.model.split("/").pop()}
          </span>
        )}
        <TierBadge tier={d.meta.tier} />
        <StatusBadge status={d.status} />
      </div>
      <p className="text-xs text-zinc-500 mb-4">
        {d.raw_count} responses · {d.scorers.length} scorers · created {d.meta.created_at || "?"}
        {d.backups.length > 0 && ` · ${d.backups.length} backup(s)`}
      </p>

      <div className="flex gap-1 mb-4 border-b border-zinc-800">
        {(["overview", "prompts", "meta"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t px-4 py-2 text-sm ${
              tab === t ? "bg-zinc-900 text-zinc-100 border-x border-t border-zinc-800 -mb-px" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t === "overview" ? "Overview" : t === "prompts" ? `Prompts (${d.raw_count})` : "Meta"}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab d={d} />}
      {tab === "prompts" && <PromptsTable />}
      {tab === "meta" && <MetaTab d={d} />}
    </div>
  );
}

function OverviewTab({ d }: { d: RunOverview }) {
  const blocks: [string, { present: boolean; rows: Record<string, string>[] }][] = [
    ["ASR summary (summary.csv)", d.summaries.asr],
    ["Refusal summary (summary_refusal.csv)", d.summaries.refusal],
    ["Crosstab ASR × Guardrail (summary_crosstab.csv)", d.summaries.crosstab],
  ];
  return (
    <div>
      {blocks.map(([title, block]) => (
        <Panel key={title} title={title}>
          <SummaryTable rows={block.rows} />
        </Panel>
      ))}
      {d.scorers.length > 0 && (
        <Panel title="Scored files">
          <div className="flex flex-wrap gap-2">
            {d.scorers.map((s) => (
              <span key={s} className="px-2 py-1 rounded bg-zinc-800 font-mono text-xs">{s}</span>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function MetaTab({ d }: { d: RunOverview }) {
  const queryClient = useQueryClient();
  const [tier, setTier] = useState(d.meta.tier);
  const [notes, setNotes] = useState(d.meta.notes);

  const save = useMutation({
    mutationFn: () =>
      api.patch(`/runs/${d.name}/meta`, {
        ...(tier !== d.meta.tier ? { tier } : {}),
        ...(notes !== d.meta.notes ? { notes } : {}),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", d.name] }),
  });

  return (
    <div className="max-w-3xl">
      <Panel title="Victim model (recorded at attack time)">
        {d.meta.victim && Object.keys(d.meta.victim).length > 0 ? (
          <table className="data">
            <tbody>
              <tr><th>Model</th><td className="font-mono">{d.meta.victim.model || "—"}</td></tr>
              <tr><th>Tier</th><td className="font-mono">{d.meta.victim.tier || "—"}</td></tr>
              <tr><th>GGUF</th><td className="font-mono">{d.meta.victim.gguf || "—"}</td></tr>
              <tr><th>Size</th><td className="font-mono">{d.meta.victim.gguf_size_mb ? `${d.meta.victim.gguf_size_mb.toLocaleString()} MB` : "—"}</td></tr>
              <tr>
                <th>SHA-256</th>
                <td className="font-mono text-[11px] break-all">
                  {d.meta.victim.gguf_sha256 ? (
                    <>
                      {d.meta.victim.gguf_sha256.slice(0, 16)}…
                      <button
                        className="ml-2 bg-zinc-800 hover:bg-zinc-700 text-[10px] px-1.5 py-0.5"
                        onClick={() => navigator.clipboard?.writeText(d.meta.victim.gguf_sha256)}
                        title="copy full hash"
                      >
                        copy
                      </button>
                    </>
                  ) : "—"}
                </td>
              </tr>
              <tr><th>LiteLLM alias</th><td className="font-mono">{d.meta.victim.litellm_model || "—"}</td></tr>
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-zinc-500">
            No victim metadata (run predates victim provenance, or attack ran without <code>--tier</code>).
          </p>
        )}
      </Panel>
      <Panel title="Run metadata (meta.json)">
      <div className="grid gap-4 max-w-xl">
        <label className="text-sm">
          <span className="text-zinc-400 block mb-1">Tier label</span>
          <input value={tier} onChange={(e) => setTier(e.target.value)} className="w-full" placeholder="e.g. Q4_K_M" />
        </label>
        <label className="text-sm">
          <span className="text-zinc-400 block mb-1">Notes</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="w-full" />
        </label>
        <div className="flex items-center gap-3">
          <button
            className="bg-sky-600 hover:bg-sky-500"
            disabled={save.isPending || (tier === d.meta.tier && notes === d.meta.notes)}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
          {save.isSuccess && <span className="text-emerald-400 text-xs">saved</span>}
          {save.isError && <span className="text-red-400 text-xs">{String(save.error)}</span>}
        </div>
        <pre className="text-xs text-zinc-500 mt-4">{JSON.stringify(d.meta, null, 2)}</pre>
      </div>
      </Panel>
    </div>
  );
}
