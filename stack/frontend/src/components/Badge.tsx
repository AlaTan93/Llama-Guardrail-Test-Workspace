import type { ReactNode } from "react";

const TONES: Record<string, string> = {
  success: "bg-emerald-500/15 text-emerald-400",
  true: "bg-emerald-500/15 text-emerald-400",
  complete: "bg-emerald-500/15 text-emerald-400",
  failure: "bg-red-500/10 text-red-400",
  false: "bg-red-500/10 text-red-400",
  error: "bg-red-500/20 text-red-400",
  undetermined: "bg-amber-500/10 text-amber-400",
  running: "bg-sky-500/15 text-sky-400",
  queued: "bg-zinc-500/15 text-zinc-400",
};

export function Badge({ value, children }: { value: string | null | undefined; children?: ReactNode }) {
  const key = String(value ?? "").toLowerCase();
  const tone = TONES[key] ?? "bg-zinc-500/15 text-zinc-300";
  return <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-mono font-semibold ${tone}`}>{children ?? key}</span>;
}
