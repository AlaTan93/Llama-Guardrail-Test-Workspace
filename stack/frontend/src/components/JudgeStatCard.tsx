import { pct } from "../lib/format";
import type { JudgeStats } from "../types";

/** One judge's headline rates. ASR is over complete attack-success verdicts;
 * refusal likewise. Undetermined gets its own row — never hidden. */
export function JudgeStatCard({ stats, primary }: { stats: JudgeStats; primary: string }) {
  const isPrimary = stats.judge_alias === primary;
  return (
    <div className="min-w-56 rounded-lg border border-zinc-800 p-3 text-xs">
      <h4 className="mb-1.5 text-xs font-semibold text-sky-400">
        {stats.judge_alias}
        {isPrimary && <span className="ml-1.5 text-[10px] text-zinc-500">(primary)</span>}
      </h4>
      <table className="w-full">
        <thead>
          <tr className="text-zinc-500">
            <th />
            <th className="text-right">ASR</th>
            <th className="text-right">Refusal</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="text-zinc-400">true</td>
            <td className="text-right font-mono">{stats.attack_success.true}</td>
            <td className="text-right font-mono">{stats.refusal.true}</td>
          </tr>
          <tr>
            <td className="text-zinc-400">false</td>
            <td className="text-right font-mono">{stats.attack_success.false}</td>
            <td className="text-right font-mono">{stats.refusal.false}</td>
          </tr>
          <tr>
            <td className="text-zinc-400">undet.</td>
            <td className="text-right font-mono text-amber-400">{stats.attack_success.undetermined}</td>
            <td className="text-right font-mono text-amber-400">{stats.refusal.undetermined}</td>
          </tr>
          <tr className="border-t border-zinc-800">
            <td className="text-zinc-400">rate</td>
            <td className="text-right font-mono font-semibold">{pct(stats.attack_success.rate_pct)}</td>
            <td className="text-right font-mono font-semibold">{pct(stats.refusal.rate_pct)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
