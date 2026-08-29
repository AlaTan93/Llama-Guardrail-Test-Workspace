// SSE subscription with token via query param (EventSource cannot set headers).

import { getToken } from "./api";
import type { JobEvent } from "./types";

export function subscribeJobEvents(
  jobId: string,
  onEvent: (e: JobEvent) => void,
  onDone?: () => void,
): () => void {
  const es = new EventSource(
    `/api/jobs/${jobId}/events?token=${encodeURIComponent(getToken())}`,
  );
  es.onmessage = (msg) => {
    const event: JobEvent = JSON.parse(msg.data);
    onEvent(event);
    if (event.type === "status" && ["done", "error", "cancelled"].includes(event.status ?? "")) {
      es.close();
      onDone?.();
    }
  };
  es.onerror = () => {
    // EventSource auto-reconnects with Last-Event-ID; terminal events close it.
  };
  return () => es.close();
}
