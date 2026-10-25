import { pct } from "../lib/format";
import { kindLabel } from "../lib/format";
import type { PairAgreement } from "../types";

/** Pairwise inter-judge agreement + Cohen's κ, per rubric, over pairs where
 * both judges produced a complete verdict. */
export function AgreementTable({ rows }: { rows: PairAgreement[] }) {
  const withPairs = rows.filter((r) => r.pairs > 0);
  if (!withPairs.length) return null;
  return (
    <div className="min-w-56 rounded-lg border border-zinc-800 p-3 text-xs">
      <h4 className="mb-1.5 text-xs font-semibold text-sky-400">Inter-judge agreement</h4>
      <table className="w-full">
        <thead>
          <tr className="text-zinc-500">
            <th className="text-left">pair</th>
            <th className="text-left">kind</th>
            <th className="text-right">agree</th>
            <th className="text-right">κ</th>
          </tr>
        </thead>
        <tbody>
          {withPairs.map((a, i) => (
            <tr key={i}>
              <td className="font-mono text-[11px]">
                {a.judge_a.replace("judge-", "")}·{a.judge_b.replace("judge-", "")}
              </td>
              <td className="text-zinc-400">{kindLabel(a.kind)}</td>
              <td className="text-right font-mono">{pct(a.agreement_pct)}</td>
              <td className="text-right font-mono">{a.kappa === null ? "—" : a.kappa.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
