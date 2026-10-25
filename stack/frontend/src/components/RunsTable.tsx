import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { fmtTime } from "../lib/format";
import type { Run } from "../types";
import { Badge } from "./Badge";

export function RunsTable({ onOpen }: { onOpen: (id: string) => void }) {
  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<Run[]>("/runs"),
    refetchInterval: 10000,
  });

  if (isLoading) return <p className="text-sm text-zinc-500">loading runs…</p>;
  if (!runs?.length) return <p className="text-sm text-zinc-500">no runs yet</p>;

  return (
    <table className="data">
      <thead>
        <tr>
          <th>created</th>
          <th>status</th>
          <th>target</th>
          <th>judges</th>
          <th>progress</th>
          <th>labels</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id}>
            <td className="font-mono text-xs">{fmtTime(r.created_at)}</td>
            <td>
              <Badge value={r.status} />
            </td>
            <td className="font-mono text-xs">{r.target_alias}</td>
            <td className="font-mono text-xs">
              {r.judges.map((j) => (
                <span key={j} className={j === r.primary_judge ? "font-bold text-sky-400" : ""}>
                  {j.replace("judge-", "")}{" "}
                </span>
              ))}
            </td>
            <td className="font-mono text-xs">
              {r.n_objectives_done}/{r.n_objectives}
            </td>
            <td className="font-mono text-xs">
              {Object.entries(r.labels ?? {})
                .map(([k, v]) => `${k}=${v}`)
                .join(" ") || "—"}
            </td>
            <td>
              <button
                onClick={() => onOpen(r.id)}
                className="rounded-md border border-zinc-700 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-800"
              >
                view
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
