import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink } from "react-router";
import type { ReactNode } from "react";
import { api, getToken, setToken, UnauthorizedError } from "../api";
import type { SystemStatus } from "../types";

const nav = [
  { to: "/", label: "Runs" },
  { to: "/jobs", label: "Jobs" },
  { to: "/new", label: "New Run" },
  { to: "/compare", label: "Compare" },
];

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-emerald-400" : "bg-zinc-600"}`}
      title={ok ? "healthy" : "down"}
    />
  );
}

function TokenGate() {
  const queryClient = useQueryClient();
  return (
    <div className="max-w-md mx-auto mt-24 p-6 bg-zinc-900 rounded-xl border border-zinc-800">
      <h2 className="text-lg font-semibold mb-2">Connect</h2>
      <p className="text-sm text-zinc-400 mb-4">
        Paste the dashboard token (printed by the backend at startup, or set
        <code className="mx-1 px-1 bg-zinc-800 rounded">WEB_TOKEN</code> in .env).
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const v = new FormData(e.currentTarget).get("token") as string;
          setToken(v);
          queryClient.invalidateQueries();
        }}
      >
        <input name="token" type="password" className="w-full" placeholder="token" autoFocus />
        <button className="mt-3 bg-sky-600 hover:bg-sky-500 w-full" type="submit">
          Connect
        </button>
      </form>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const system = useQuery<SystemStatus>({
    queryKey: ["system"],
    queryFn: () => api.get<SystemStatus>("/system"),
    refetchInterval: 10_000,
    retry: false,
  });

  const unauthorized = !getToken() || system.error instanceof UnauthorizedError;
  if (unauthorized) {
    return (
      <div className="min-h-screen">
        <header className="border-b border-zinc-800">
          <div className="max-w-[100rem] mx-auto px-4 py-3 font-semibold tracking-tight">
            redteam<span className="text-sky-400">.dash</span>
          </div>
        </header>
        <main className="max-w-[100rem] mx-auto px-4 py-6">
          <TokenGate />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 bg-zinc-950/90 sticky top-0 z-10">
        <div className="max-w-[100rem] mx-auto px-4 py-3 flex items-center gap-6">
          <span className="font-semibold tracking-tight">
            redteam<span className="text-sky-400">.dash</span>
          </span>
          <nav className="flex gap-1">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm ${
                    isActive ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-4 text-xs text-zinc-400">
            {system.data && (
              <>
                <span className="flex items-center gap-1.5">
                  <Dot ok={system.data.servers.victim_8080} /> victim
                </span>
                <span className="flex items-center gap-1.5">
                  <Dot ok={system.data.servers.bf16_8081} /> bf16
                </span>
                <span className="flex items-center gap-1.5">
                  <Dot ok={system.data.servers.litellm_4000} /> litellm
                </span>
                {system.data.queue.current && (
                  <span className="px-2 py-0.5 rounded bg-amber-900/50 text-amber-300">
                    {system.data.queue.current.kind} running
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-[100rem] mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
