import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { api } from "../api";
import type { JobRecord } from "../types";

/** Shared job-submission mutation: on success, jump to the live job console. */
export function useSubmitJob(invalidateKeys: string[][] = []) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return useMutation({
    mutationFn: (body: { kind: string; params: Record<string, unknown> }) =>
      api.post<JobRecord>("/jobs", body),
    onSuccess: (job) => {
      for (const key of invalidateKeys) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/jobs/${job.id}`);
    },
  });
}
