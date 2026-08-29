import { useParams } from "react-router";
import { JobConsole } from "../components/jobs/JobConsole";
import { JobList } from "../components/jobs/JobList";

export function Jobs() {
  const { jobId } = useParams<{ jobId?: string }>();
  const selected = jobId ?? null;

  return (
    <div className={selected ? "grid gap-6 lg:grid-cols-[22rem_1fr]" : ""}>
      <JobList selected={selected} />
      {selected && <JobConsole key={selected} jobId={selected} />}
    </div>
  );
}
