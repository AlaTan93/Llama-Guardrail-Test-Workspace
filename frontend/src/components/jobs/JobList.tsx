import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../../api";
import type { JobRecord } from "../../types";
import { StatusBadge } from "../ui";

export function JobList({ selected }: { selected: string | null }) {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<{ jobs: JobRecord[] }>("/jobs"),
    refetchInterval: (q) => {
      const list = q.state.data?.jobs ?? [];
      return list.some((j) => ["queued", "running"].includes(j.status)) ? 2_000 : 10_000;
    },
  });

  const cancel = useMutation({
    mutationFn: (id: string) => api.post(`/jobs/${id}/cancel`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  if (jobs.isLoading) return <p className="text-zinc-500">Loading jobs…</p>;
  if (jobs.error) return <p className="text-red-400">{String(jobs.error)}</p>;

  return (
    <div className="overflow-auto rounded-lg border border-zinc-800">
      <table className="data">
        <thead>
          <tr>
            <th>Job</th>
            <th>Kind</th>
            <th>Run</th>
            <th>Status</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {jobs.data!.jobs.map((j) => (
            <tr key={j.id} className={j.id === selected ? "bg-sky-950/40" : undefined}>
              <td>
                <Link to={`/jobs/${j.id}`} className="text-sky-400 hover:underline font-mono text-xs">
                  {j.id}
                </Link>
              </td>
              <td className="text-xs">{j.kind}{j.params?.tier ? `:${String(j.params.tier)}` : ""}</td>
              <td className="text-xs font-mono text-zinc-400">{j.run_name ?? "—"}</td>
              <td><StatusBadge status={j.status} /></td>
              <td className="text-xs text-zinc-500">{j.created_at}</td>
              <td>
                {["queued", "running"].includes(j.status) && (
                  <button
                    className="bg-red-900/60 hover:bg-red-800 text-xs px-2 py-0.5"
                    onClick={() => cancel.mutate(j.id)}
                  >
                    cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
