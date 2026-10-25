import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { subscribeRun } from "../lib/sse";

/** Live progress for a run: on every SSE tick, refresh run + objectives +
 * stats queries; close when the run reaches a terminal status. */
export function useRunStream(runId: string, status: string | undefined) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!status || status === "complete" || status === "error") return;
    const close = subscribeRun(runId, {
      onRun: () => {
        void queryClient.invalidateQueries({ queryKey: ["run", runId] });
        void queryClient.invalidateQueries({ queryKey: ["objectives", runId] });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
      },
      onDone: () => {
        void queryClient.invalidateQueries({ queryKey: ["run", runId] });
        void queryClient.invalidateQueries({ queryKey: ["objectives", runId] });
        void queryClient.invalidateQueries({ queryKey: ["stats", runId] });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
      },
    });
    return close;
  }, [runId, status, queryClient]);
}
