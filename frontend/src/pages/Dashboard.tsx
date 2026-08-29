import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api";
import type { RunSummary } from "../types";
import { StatusBadge, TierBadge } from "../components/ui";

export function Dashboard() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<{ runs: RunSummary[] }>("/runs"),
    refetchInterval: (q) =>
      q.state.data?.runs.some((r) => r.status === "running") ? 3_000 : 15_000,
  });

  if (runs.isLoading) return <p className="text-zinc-500">Loading runs…</p>;
  if (runs.error) return <p className="text-red-400">{String(runs.error)}</p>;

  const list = runs.data!.runs;

  return (
    <div>
      <div className="flex items-center mb-4">
        <h1 className="text-xl font-semibold">Runs</h1>
        <div className="ml-auto flex gap-2">
          <Link to="/new" className="bg-sky-600 hover:bg-sky-500 text-sm">
            + New Run
          </Link>
          <Link to="/compare" className="bg-zinc-800 hover:bg-zinc-700 text-sm">
            Compare
          </Link>
        </div>
      </div>

      <div className="overflow-auto rounded-xl border border-zinc-800">
        <table className="data">
          <thead>
            <tr>
              <th>Run</th>
              <th>Victim</th>
              <th>Tier</th>
              <th>Status</th>
              <th>Prompts</th>
              <th>Dataset</th>
              <th>Created</th>
              <th>Scored coverage</th>
              <th>Summaries</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => {
              const expected = Math.max(r.raw_count, 1);
              const scored = Object.values(r.scored_counts);
              const worst = scored.length ? Math.min(...scored) : 0;
              const covered = (worst / expected) * 100;
              return (
                <tr key={r.name}>
                  <td>
                    <Link to={`/runs/${r.name}`} className="text-sky-400 hover:underline font-mono text-xs">
                      {r.name}
                    </Link>
                  </td>
                  <td className="text-xs text-zinc-300" title={r.victim_model}>
                    {r.victim_model ? r.victim_model.split("/").pop() : "—"}
                  </td>
                  <td><TierBadge tier={r.tier} /></td>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="font-mono">{r.raw_count}</td>
                  <td className="font-mono">{r.dataset_size ?? "—"}</td>
                  <td className="text-xs text-zinc-400">{r.created_at || "—"}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-28 h-1.5 bg-zinc-800 rounded overflow-hidden">
                        <div
                          className={`h-full ${covered >= 100 ? "bg-emerald-500" : "bg-amber-500"}`}
                          style={{ width: `${Math.min(100, covered)}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-zinc-500 font-mono">
                        {worst}/{expected}
                      </span>
                    </div>
                  </td>
                  <td className="text-xs">
                    {(["asr", "refusal", "crosstab"] as const).map((s) => (
                      <span key={s} className={r.summaries[s] ? "text-emerald-400" : "text-zinc-600"}>
                        {s[0].toUpperCase()}{" "}
                      </span>
                    ))}
                  </td>
                  <td className="text-xs text-zinc-500 max-w-48 truncate">{r.notes}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
