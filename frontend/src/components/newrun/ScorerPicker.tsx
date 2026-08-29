const needsGpu = (m: string) => m.endsWith("_bf16") || m.endsWith("_pyrit");

/** Scorer checkboxes (+ GPU hints) and optional conversation-id subset. */
export function ScorerPicker({
  scorers,
  selected,
  onToggle,
  conversationIds,
  onConversationIds,
  warnNoTier,
}: {
  scorers: string[];
  selected: Set<string>;
  onToggle: (m: string) => void;
  conversationIds: string;
  onConversationIds: (v: string) => void;
  warnNoTier: boolean;
}) {
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {scorers.map((m) => (
          <label
            key={m}
            className={`px-2 py-1 rounded text-xs font-mono cursor-pointer border ${
              selected.has(m) ? "bg-sky-950 border-sky-700" : "bg-zinc-900 border-zinc-800"
            }`}
          >
            <input
              type="checkbox"
              className="mr-1 accent-sky-500 hidden"
              checked={selected.has(m)}
              onChange={() => onToggle(m)}
            />
            {m} {needsGpu(m) && <span className="text-amber-400" title="requires local GPU server">GPU</span>}
          </label>
        ))}
      </div>
      <label className="text-sm block mt-4">
        <span className="text-zinc-400 block mb-1">
          Conversation IDs (optional — one per line; empty = score everything unscored)
        </span>
        <textarea
          rows={3}
          value={conversationIds}
          onChange={(e) => onConversationIds(e.target.value)}
          className="w-full font-mono text-xs"
        />
      </label>
      {warnNoTier && (
        <p className="text-xs text-amber-400 mt-2">
          Run has no tier label and *_pyrit scorers need the victim model — set the tier in the run's Meta tab first.
        </p>
      )}
    </div>
  );
}
