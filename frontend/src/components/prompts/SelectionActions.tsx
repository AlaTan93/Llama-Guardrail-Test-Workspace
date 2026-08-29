import type { SystemStatus } from "../../types";

interface Props {
  selectedCount: number;
  scorers: string[];
  rescoreModels: Set<string>;
  onToggleRescoreModel: (m: string) => void;
  attackTier: string;
  onAttackTierChange: (tier: string) => void;
  tiers: SystemStatus["tiers"];
  runTier: string;
  objectives: string[];
  onRescore: (models: string[]) => void;
  onReattack: (tier: string) => void;
  onClear: () => void;
  error: unknown;
}

/** Action bar shown when prompts are selected: partial re-score / re-attack. */
export function SelectionActions(p: Props) {
  const effectiveTier = p.attackTier || p.runTier;
  return (
    <div className="mb-3 p-3 rounded-lg bg-zinc-900 border border-zinc-700 flex flex-wrap items-center gap-3">
      <span className="text-sm font-medium">{p.selectedCount} selected</span>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-zinc-400">re-score with:</span>
        {p.scorers.map((s) => (
          <label key={s} className="text-xs font-mono flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              className="accent-sky-500"
              checked={p.rescoreModels.has(s)}
              onChange={() => p.onToggleRescoreModel(s)}
            />
            {s}
          </label>
        ))}
        <button
          className="bg-sky-600 hover:bg-sky-500"
          disabled={p.rescoreModels.size === 0}
          onClick={() => p.onRescore([...p.rescoreModels])}
        >
          Re-score
        </button>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-zinc-400">re-attack on tier:</span>
        <select value={effectiveTier} onChange={(e) => p.onAttackTierChange(e.target.value)}>
          <option value="" disabled>select tier…</option>
          {p.tiers.map((t) => (
            <option key={t.tier} value={t.tier} disabled={!t.available}>
              {t.tier}{t.available ? "" : " (GGUF missing)"}
            </option>
          ))}
        </select>
        <button
          className="bg-amber-700 hover:bg-amber-600"
          disabled={!effectiveTier}
          title="Re-runs these objectives against the victim; old responses are backed up and replaced"
          onClick={() => p.onReattack(effectiveTier)}
        >
          Re-attack
        </button>
      </div>
      <button className="ml-auto bg-zinc-800 hover:bg-zinc-700" onClick={p.onClear}>
        Clear
      </button>
      {p.error != null && (
        <span className="text-red-400 text-sm w-full">Job submit failed: {String(p.error)}</span>
      )}
    </div>
  );
}
