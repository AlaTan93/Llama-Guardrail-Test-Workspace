import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api } from "../../api";
import { subscribeJobEvents } from "../../sse";
import type { JobEvent, JobRecord } from "../../types";
import { Panel, ProgressBar, StatusBadge } from "../ui";

/** Live console for one job: SSE log stream, per-scorer progress, params. */
export function JobConsole({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<JobRecord>(`/jobs/${jobId}`),
  });

  const [lines, setLines] = useState<string[]>([]);
  const [progress, setProgress] = useState<Record<string, { done: number; total: number }>>({});
  const [phase, setPhase] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const consoleRef = useRef<HTMLPreElement>(null);

  // Subscribe once per jobId: the SSE endpoint replays full history (from seq 0)
  // for both live and terminal jobs, so no client-side seeding is needed.
  useEffect(() => {
    setLines([]);
    setProgress({});
    setPhase("");
    setStatus("");
    const unsub = subscribeJobEvents(
      jobId,
      (ev: JobEvent) => {
        if (ev.type === "log" && ev.line) setLines((prev) => [...prev.slice(-2000), ev.line!]);
        else if (ev.type === "progress" && ev.scorer) {
          setProgress((prev) => ({ ...prev, [ev.scorer!]: { done: ev.done ?? 0, total: ev.total ?? 0 } }));
        } else if (ev.type === "phase" && ev.phase) setPhase(ev.phase);
        else if (ev.type === "status" && ev.status) setStatus(ev.status);
      },
      () => {
        queryClient.invalidateQueries({ queryKey: ["job", jobId] });
        queryClient.invalidateQueries({ queryKey: ["jobs"] });
        queryClient.invalidateQueries({ queryKey: ["runs"] });
        queryClient.invalidateQueries({ queryKey: ["run"] });
      },
    );
    return unsub;
  }, [jobId, queryClient]);

  useEffect(() => {
    consoleRef.current?.scrollTo({ top: consoleRef.current.scrollHeight });
  }, [lines]);

  const rec = job.data;
  if (!rec) return <p className="text-zinc-500">Loading job…</p>;

  const isTerminal = ["done", "error", "cancelled"].includes(status);

  return (
    <div>
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <h1 className="text-lg font-mono">{rec.id}</h1>
        <StatusBadge status={status || rec.status} />
        {phase && <span className="text-xs px-2 py-0.5 rounded bg-zinc-800">phase: {phase}</span>}
        {rec.params?.tier ? (
          <span className="text-xs font-mono text-indigo-300">{String(rec.params.tier)}</span>
        ) : null}
        {rec.run_name && (
          <Link to={`/runs/${rec.run_name}`} className="text-xs font-mono text-sky-400 hover:underline">
            {rec.run_name}
          </Link>
        )}
      </div>

      {!isTerminal && Object.keys(progress).length > 0 && (
        <Panel title="Progress">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(progress).map(([name, p]) => (
              <div key={name}>
                <div className="text-xs font-mono text-zinc-400 mb-1">{name}</div>
                <ProgressBar done={p.done} total={p.total} />
              </div>
            ))}
          </div>
        </Panel>
      )}

      {rec.error && (
        <div className="mb-4 p-3 rounded bg-red-950/60 border border-red-900 text-xs font-mono whitespace-pre-wrap max-h-48 overflow-auto">
          {rec.error}
        </div>
      )}

      <Panel title="Console (live)">
        <pre ref={consoleRef} className="logconsole">
          {lines.join("\n") || "(no output yet)"}
        </pre>
      </Panel>

      <Panel title="Params">
        <pre className="text-xs text-zinc-400">{JSON.stringify(rec.params, null, 2)}</pre>
      </Panel>
    </div>
  );
}
