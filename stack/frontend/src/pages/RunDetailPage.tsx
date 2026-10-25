import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api } from "../lib/api";
import type { Objective, Run, RunStats } from "../types";
import { AgreementTable } from "../components/AgreementTable";
import { Badge } from "../components/Badge";
import { Conversation } from "../components/Conversation";
import { DivergenceCard } from "../components/DivergenceCard";
import { JudgeStatCard } from "../components/JudgeStatCard";
import { VerdictMatrix } from "../components/VerdictMatrix";
import { useRunStream } from "../hooks/useRunStream";

function StatsPanel({ stats, primary }: { stats: RunStats; primary: string }) {
  if (!stats.per_judge?.length) return null;
  return (
    <div className="flex flex-wrap gap-3">
      {stats.per_judge.map((j) => (
        <JudgeStatCard key={j.judge_alias} stats={j} primary={primary} />
      ))}
      <AgreementTable rows={stats.agreement ?? []} />
      <DivergenceCard divergence={stats.self_divergence ?? null} />
    </div>
  );
}

function ObjectivesTable({ objectives }: { objectives: Objective[] }) {
  if (!objectives.length) {
    return <p className="text-sm text-zinc-500">waiting for the first objective…</p>;
  }
  return (
    <table className="data">
      <thead>
        <tr>
          <th>#</th>
          <th>objective</th>
          <th>outcome</th>
          <th>verdict matrix</th>
        </tr>
      </thead>
      <tbody>
        {objectives.map((o) => (
          <tr key={o.id}>
            <td className="font-mono text-xs">{o.seq + 1}</td>
            <td className="max-w-md break-words">
              {o.prompt}
              <Conversation objective={o} />
            </td>
            <td>
              {o.outcome ? <Badge value={o.outcome} /> : <span className="text-zinc-500">—</span>}
              {o.execution_time_ms !== null && (
                <div className="mt-0.5 font-mono text-[10px] text-zinc-500">{o.execution_time_ms} ms</div>
              )}
            </td>
            <td>
              <VerdictMatrix scores={o.scores ?? []} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function RunDetailPage() {
  const { runId = "" } = useParams();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.get<Run>(`/runs/${runId}`) });
  const objectives = useQuery({
    queryKey: ["objectives", runId],
    queryFn: () => api.get<Objective[]>(`/runs/${runId}/objectives`),
  });
  const stats = useQuery({
    queryKey: ["stats", runId],
    queryFn: () => api.get<RunStats>(`/runs/${runId}/stats`),
    enabled: !!run.data,
  });
  useRunStream(runId, run.data?.status);

  if (run.isLoading) return <p className="text-sm text-zinc-500">loading run…</p>;
  if (run.isError || !run.data) return <p className="text-sm text-red-400">run not found</p>;

  const r = run.data;

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link to="/" className="text-xs text-sky-400 hover:underline">
            ← runs
          </Link>
          <h2 className="mt-1 font-mono text-base">
            run {r.id.slice(0, 8)} · {r.target_alias}
          </h2>
          <div className="mt-1 font-mono text-xs text-zinc-400">
            status <Badge value={r.status} /> · progress {r.n_objectives_done}/{r.n_objectives} · judges{" "}
            {r.judges.map((j) => (j === r.primary_judge ? `*${j}` : j)).join(", ")}
            {Object.entries(r.labels ?? {}).length > 0 && (
              <> · {Object.entries(r.labels).map(([k, v]) => `${k}=${v}`).join(" ")}</>
            )}
          </div>
          {r.error && <div className="mt-1 max-w-3xl break-words font-mono text-xs text-red-400">{r.error}</div>}
        </div>
      </div>

      <section className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Per-judge summary</h3>
        {stats.data ? (
          <StatsPanel stats={stats.data} primary={r.primary_judge} />
        ) : (
          <p className="text-sm text-zinc-500">no scores yet</p>
        )}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Objectives</h3>
        {objectives.isLoading ? (
          <p className="text-sm text-zinc-500">loading…</p>
        ) : (
          <ObjectivesTable objectives={objectives.data ?? []} />
        )}
      </section>
    </>
  );
}
