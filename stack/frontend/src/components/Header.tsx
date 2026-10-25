import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Health } from "../types";

export function Header() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<Health>("/health"),
    refetchInterval: 15000,
  });

  return (
    <header className="flex items-center justify-between border-b border-zinc-800 px-6 py-3">
      <h1 className="text-lg font-semibold">
        Guardrail Testing <span className="text-sky-400">v2</span>
      </h1>
      <div className="text-xs font-mono text-zinc-400">
        {!health ? (
          "checking…"
        ) : (
          <>
            db <span className={health.database ? "text-emerald-400" : "text-red-400"}>{health.database ? "✓" : "✗"}</span>
            {" · "}
            litellm <span className={health.litellm ? "text-emerald-400" : "text-red-400"}>{health.litellm ? "✓" : "✗"}</span>
            {" · "}
            target {health.target_alias} · primary {health.primary_judge}
          </>
        )}
      </div>
    </header>
  );
}
