import type { ReactNode } from "react";

export function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    complete: "bg-emerald-900/60 text-emerald-300",
    partial: "bg-amber-900/60 text-amber-300",
    new: "bg-zinc-800 text-zinc-400",
    empty: "bg-zinc-800 text-zinc-500",
    running: "bg-sky-900/60 text-sky-300 animate-pulse",
    queued: "bg-zinc-800 text-zinc-300",
    done: "bg-emerald-900/60 text-emerald-300",
    error: "bg-red-900/60 text-red-300",
    cancelled: "bg-zinc-800 text-zinc-400",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${cls[status] ?? cls.new}`}>
      {status}
    </span>
  );
}

export function TierBadge({ tier }: { tier: string }) {
  if (!tier) return <span className="text-zinc-600 text-xs">—</span>;
  return (
    <span className="px-2 py-0.5 rounded text-xs font-mono bg-indigo-900/50 text-indigo-300">
      {tier}
    </span>
  );
}

const SCORE_STYLE: Record<string, string> = {
  true: "bg-emerald-900/60 text-emerald-300",
  false: "bg-zinc-800 text-zinc-300",
  error: "bg-red-900/60 text-red-300",
  undetermined: "bg-zinc-700 text-zinc-300",
  content_policy_violation: "bg-fuchsia-900/60 text-fuchsia-300",
};

const SCORE_SHORT: Record<string, string> = {
  true: "T",
  false: "F",
  error: "E",
  undetermined: "U",
  content_policy_violation: "CPV",
};

export function ScoreChip({ value, title }: { value: string; title?: string }) {
  return (
    <span
      title={title ?? value}
      className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-mono ${SCORE_STYLE[value] ?? "bg-zinc-800"}`}
    >
      {SCORE_SHORT[value] ?? value}
    </span>
  );
}

const QUADRANT_STYLE: Record<string, string> = {
  breach: "bg-red-900/70 text-red-200",
  scarecrow: "bg-amber-900/70 text-amber-200",
  guarded: "bg-emerald-900/70 text-emerald-200",
  fizzle: "bg-sky-900/70 text-sky-200",
};

export function QuadrantChip({ q }: { q: string | null }) {
  if (!q) return <span className="text-zinc-600 text-xs">—</span>;
  const icon = { breach: "⛔", scarecrow: "🎃", guarded: "🛡", fizzle: "💨" }[q];
  return (
    <span className={`px-1.5 py-0.5 rounded text-[11px] ${QUADRANT_STYLE[q]}`} title={q}>
      {icon} {q}
    </span>
  );
}

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;
  return (
    <div className="w-full">
      <div className="h-2 bg-zinc-800 rounded overflow-hidden">
        <div className="h-full bg-sky-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[11px] text-zinc-500 mt-0.5">
        {done}/{total || "?"}
      </div>
    </div>
  );
}

export function Panel({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="bg-zinc-900/60 rounded-xl border border-zinc-800 mb-6">
      <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center">
        <h2 className="text-sm font-semibold text-zinc-300">{title}</h2>
        <div className="ml-auto">{right}</div>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function SummaryTable({ rows }: { rows: Record<string, string>[] }) {
  if (!rows.length) return <p className="text-sm text-zinc-500">No data.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="overflow-auto">
      <table className="data">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} className={c === "metric" ? "font-mono text-zinc-400 whitespace-nowrap" : "font-mono"}>
                  {r[c] === "" ? "—" : r[c]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
