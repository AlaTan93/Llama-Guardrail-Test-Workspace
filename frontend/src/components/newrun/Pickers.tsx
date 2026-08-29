import type { SystemStatus } from "../../types";

/** Victim tier button grid + dataset size (used by e2e / attack modes). */
export function TierPicker({
  tiers,
  tier,
  onTier,
  datasetSize,
  onDatasetSize,
}: {
  tiers: SystemStatus["tiers"];
  tier: string;
  onTier: (t: string) => void;
  datasetSize: number;
  onDatasetSize: (n: number) => void;
}) {
  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-3">
        {tiers.map((t) => (
          <button
            key={t.tier}
            disabled={!t.available}
            title={t.available ? t.gguf : `${t.gguf} missing`}
            onClick={() => onTier(t.tier)}
            className={`font-mono text-xs ${tier === t.tier ? "bg-indigo-600 hover:bg-indigo-500" : "bg-zinc-800 hover:bg-zinc-700"} ${t.available ? "" : "opacity-40"}`}
          >
            {t.tier}
          </button>
        ))}
      </div>
      <label className="text-sm flex items-center gap-2">
        <span className="text-zinc-400">Dataset size (HarmBench objectives)</span>
        <input
          type="number"
          min={1}
          value={datasetSize}
          onChange={(e) => onDatasetSize(Number(e.target.value))}
          className="w-24"
        />
      </label>
    </div>
  );
}

export function RunPicker({
  runs,
  value,
  onChange,
  label,
  optional,
}: {
  runs: { name: string; tier: string }[];
  value: string;
  onChange: (v: string) => void;
  label: string;
  optional?: boolean;
}) {
  return (
    <label className="text-sm block">
      <span className="text-zinc-400 block mb-1">
        {label}
        {optional && " (optional)"}
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {optional && <option value="">(none)</option>}
        <option value="">select run…</option>
        {runs.map((r) => (
          <option key={r.name} value={r.name}>
            {r.name} {r.tier && `(${r.tier})`}
          </option>
        ))}
      </select>
    </label>
  );
}
