import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { RunSummary, SystemStatus } from "../types";
import { Panel } from "../components/ui";
import { RunPicker, TierPicker } from "../components/newrun/Pickers";
import { ScorerPicker } from "../components/newrun/ScorerPicker";
import { useSubmitJob } from "../hooks/useSubmitJob";

type Mode = "e2e" | "attack" | "rescore" | "summarize" | "merge";

const MODES: { value: Mode; label: string; help: string }[] = [
  { value: "e2e", label: "E2E tier run", help: "Full pipeline for a tier: attacks, both scoring phases, summaries. Backend manages llama.cpp servers." },
  { value: "attack", label: "Attack only", help: "Run attacks (new run), or re-attack selected objectives into an existing run." },
  { value: "rescore", label: "Re-score", help: "Score an existing run's responses with selected judges. Resumable; skips already-scored rows." },
  { value: "summarize", label: "Summarize", help: "Regenerate summary CSVs from the scored files present in a run." },
  { value: "merge", label: "Merge runs", help: "Merge source runs into a target run directory." },
];

export function NewRun() {
  const [mode, setMode] = useState<Mode>("e2e");
  const [tier, setTier] = useState("");
  const [datasetSize, setDatasetSize] = useState(400);
  const [runName, setRunName] = useState("");
  const [objectives, setObjectives] = useState("");
  const [models, setModels] = useState<Set<string>>(new Set());
  const [conversationIds, setConversationIds] = useState("");
  const [mergeSources, setMergeSources] = useState<Set<string>>(new Set());

  const system = useQuery({
    queryKey: ["system"],
    queryFn: () => api.get<SystemStatus>("/system"),
  });
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<{ runs: RunSummary[] }>("/runs"),
  });

  const submit = useSubmitJob([["runs"]]);

  const allRuns = runs.data?.runs ?? [];
  const currentRun = allRuns.find((r) => r.name === runName);

  function buildJob(): { kind: string; params: Record<string, unknown> } | null {
    if (mode === "e2e" || mode === "attack") {
      if (!tier) return null;
      const params: Record<string, unknown> = { tier, dataset_size: datasetSize };
      if (mode === "attack" && runName) {
        const objs = objectives.split("\n").map((s) => s.trim()).filter(Boolean);
        if (!objs.length) return null;
        params.run_name = runName;
        params.objectives = objs;
      }
      return { kind: mode, params };
    }
    if (mode === "rescore") {
      if (!runName || !models.size) return null;
      const params: Record<string, unknown> = { run_name: runName, models: [...models] };
      const cids = conversationIds.split("\n").map((s) => s.trim()).filter(Boolean);
      if (cids.length) params.conversation_ids = cids;
      return { kind: "rescore", params };
    }
    if (mode === "summarize") {
      if (!runName) return null;
      return { kind: "summarize", params: { run_name: runName } };
    }
    if (mode === "merge") {
      if (!runName || !mergeSources.size) return null;
      return { kind: "merge", params: { target: runName, sources: [...mergeSources] } };
    }
    return null;
  }

  const job = buildJob();

  function toggleModel(m: string) {
    setModels((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m);
      else next.add(m);
      return next;
    });
  }

  function toggleSource(name: string) {
    setMergeSources((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-xl font-semibold mb-4">New Run</h1>

      <Panel title="Mode">
        <div className="flex flex-wrap gap-2 mb-3">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={mode === m.value ? "bg-sky-600 hover:bg-sky-500" : "bg-zinc-800 hover:bg-zinc-700"}
            >
              {m.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-zinc-500">{MODES.find((m) => m.value === mode)!.help}</p>
      </Panel>

      {(mode === "e2e" || mode === "attack") && (
        <Panel title="Victim tier">
          <TierPicker
            tiers={system.data?.tiers ?? []}
            tier={tier}
            onTier={setTier}
            datasetSize={datasetSize}
            onDatasetSize={setDatasetSize}
          />
          {mode === "attack" && (
            <div className="mt-4 grid gap-2">
              <RunPicker
                runs={allRuns}
                value={runName}
                onChange={setRunName}
                label="Existing run (leave empty for a new run; set + objectives = in-place re-attack)"
                optional
              />
              {runName && (
                <label className="text-sm">
                  <span className="text-zinc-400 block mb-1">Objectives (one per line)</span>
                  <textarea
                    rows={4}
                    value={objectives}
                    onChange={(e) => setObjectives(e.target.value)}
                    className="w-full font-mono text-xs"
                    placeholder="paste objective texts from the Prompts tab…"
                  />
                </label>
              )}
            </div>
          )}
        </Panel>
      )}

      {(mode === "rescore" || mode === "summarize" || mode === "merge") && (
        <Panel title="Run">
          <RunPicker runs={allRuns} value={runName} onChange={setRunName} label="Run" />
        </Panel>
      )}

      {mode === "rescore" && runName && (
        <Panel title="Scorers">
          <ScorerPicker
            scorers={system.data?.scorers ?? []}
            selected={models}
            onToggle={toggleModel}
            conversationIds={conversationIds}
            onConversationIds={setConversationIds}
            warnNoTier={
              !currentRun?.tier &&
              [...models].some((m) => m.endsWith("_pyrit"))
            }
          />
        </Panel>
      )}

      {mode === "merge" && runName && (
        <Panel title="Sources">
          <div className="grid gap-1 max-h-64 overflow-auto">
            {allRuns.filter((r) => r.name !== runName).map((r) => (
              <label key={r.name} className="text-xs font-mono flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="accent-sky-500"
                  checked={mergeSources.has(r.name)}
                  onChange={() => toggleSource(r.name)}
                />
                {r.name} {r.tier && `(${r.tier})`}
              </label>
            ))}
          </div>
        </Panel>
      )}

      <div className="flex items-center gap-3">
        <button
          className="bg-sky-600 hover:bg-sky-500"
          disabled={!job || submit.isPending}
          onClick={() => job && submit.mutate(job)}
        >
          {submit.isPending ? "Submitting…" : "Submit job"}
        </button>
        {submit.isError && <span className="text-red-400 text-sm">{String(submit.error)}</span>}
        {mode === "attack" && runName && (
          <span className="text-xs text-amber-400">
            Re-attack replaces responses (backups kept) and invalidates their scores.
          </span>
        )}
      </div>

      {job && <pre className="mt-4 text-xs text-zinc-500">{JSON.stringify(job, null, 2)}</pre>}
    </div>
  );
}
