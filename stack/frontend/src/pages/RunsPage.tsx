import { NewRunForm } from "../components/NewRunForm";
import { RunsTable } from "../components/RunsTable";

export default function RunsPage({ onOpen }: { onOpen: (id: string) => void }) {
  return (
    <>
      <NewRunForm />
      <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="mb-3 text-sm font-semibold">Runs</h2>
        <RunsTable onOpen={onOpen} />
      </section>
    </>
  );
}
