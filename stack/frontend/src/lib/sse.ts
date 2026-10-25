/** SSE subscription for /api/runs/{id}/events — "run" progress + "done". */

export type RunEventHandlers = {
  onRun?: (payload: unknown) => void;
  onDone?: () => void;
};

export function subscribeRun(runId: string, handlers: RunEventHandlers): () => void {
  const source = new EventSource(`/api/runs/${runId}/events`);
  source.addEventListener("run", (ev) => {
    try {
      handlers.onRun?.(JSON.parse((ev as MessageEvent).data));
    } catch {
      /* ignore malformed frame */
    }
  });
  source.addEventListener("done", () => {
    source.close();
    handlers.onDone?.();
  });
  source.onerror = () => {
    // server closed the stream (or run terminal) — EventSource auto-retries;
    // the done handler + query invalidation cover the terminal case.
  };
  return () => source.close();
}
