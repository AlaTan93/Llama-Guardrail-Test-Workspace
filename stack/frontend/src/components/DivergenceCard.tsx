import { pct } from "../lib/format";
import type { SelfDivergence } from "../types";

/** How judge-self diverges from the primary judge — the self-judge bias panel. */
export function DivergenceCard({ divergence }: { divergence: SelfDivergence | null }) {
  if (!divergence) return null;
  return (
    <div className="min-w-56 rounded-lg border border-zinc-800 p-3 text-xs">
      <h4 className="mb-1.5 text-xs font-semibold text-sky-400">
        Self-judge divergence <span className="text-[10px] text-zinc-500">vs {divergence.primary_judge}</span>
      </h4>
      <table className="w-full">
        <tbody>
          <tr>
            <td className="text-zinc-400">self-lenience (ASR)</td>
            <td className="text-right font-mono font-semibold">{pct(divergence.attack_success.lenience_pct)}</td>
          </tr>
          <tr>
            <td className="text-zinc-400">self-strictness (ASR)</td>
            <td className="text-right font-mono font-semibold">{pct(divergence.attack_success.strictness_pct)}</td>
          </tr>
          <tr>
            <td className="text-zinc-400">refusal blindness</td>
            <td className="text-right font-mono font-semibold">{pct(divergence.refusal.blindness_pct)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
