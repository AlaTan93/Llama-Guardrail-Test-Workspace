"""Job runners: bridge the JobManager to the pipeline modules.

Each runner orchestrates llama.cpp server lifecycle (via ``asyncio.to_thread``
so the web event loop stays responsive), invokes the pipeline, and emits
progress events through the job.
"""

import asyncio
from pathlib import Path

import src.patches  # noqa: F401  PyRIT JSON-normalization patches, must load before pyrit use
from src import e2e as e2e_mod
from src import redteam, scoring, tiers
from src.config import RESULTS_DIR
from src.csv_io import backup_file, load_raw_responses
from src.progress import ProgressReporter
from src.run_meta import read_meta, update_meta
from src.scorers import SCORER_SPECS
from src.servers import ServerStack
from src.victim_meta import build_victim_block
from src.web import runs

# ── helpers ────────────────────────────────────────────────────────

class JobProgress(ProgressReporter):
    """Bridges :class:`src.progress.ProgressReporter` into job SSE events."""

    def __init__(self, job):
        self.job = job

    def attack_total(self, total: int) -> None:
        self.job.progress["attack"] = {"done": 0, "total": total}
        self.job.emit({"type": "event", "event": "attack_total", "total": total})

    def attack_done(self, rows: int) -> None:
        if "attack" in self.job.progress:
            self.job.progress["attack"]["done"] = self.job.progress["attack"]["total"]
        self.job.emit({"type": "event", "event": "attack_done", "rows": rows})

    def scorer_tick(self, scorer_type: str, done: int, total: int) -> None:
        self.job.progress[scorer_type] = {"done": done, "total": total}
        self.job.emit({"type": "progress", "scorer": scorer_type, "done": done, "total": total})

    def phase(self, name: str) -> None:
        self.job.emit({"type": "phase", "phase": name})


async def _poll_attack_progress(job, attack_task: asyncio.Task, interval: float = 2.0) -> None:
    """Approximate live attack progress by counting PyRIT attack results."""
    from pyrit.memory import CentralMemory

    while not attack_task.done():
        try:
            mem = CentralMemory.get_memory_instance()
            results = mem.get_attack_results()
            done = len({r.conversation_id for r in results})
            total = job.progress.get("attack", {}).get("total") or 0
            job.progress["attack"] = {"done": done, "total": total}
            job.emit({"type": "progress", "scorer": "attack", "done": done, "total": total})
        except Exception:
            pass  # memory not initialised yet — retry next tick
        await asyncio.sleep(interval)


async def _summarize_run(run_dir: str) -> None:
    from src.summaries import write_summaries

    d = runs.run_path(Path(run_dir).name)
    scorers = sorted(p.stem.removeprefix("scored_") for p in d.glob("scored_*.csv"))
    if not scorers:
        return
    responses = load_raw_responses(str(d))
    await asyncio.to_thread(write_summaries, str(d), scorers, responses)


# ── runners ────────────────────────────────────────────────────────

async def run_job(job) -> None:
    if job.kind == "e2e":
        await _run_e2e(job)
    elif job.kind == "attack":
        await _run_attack(job)
    elif job.kind == "rescore":
        await _run_rescore(job)
    elif job.kind == "summarize":
        await _run_summarize(job)
    elif job.kind == "merge":
        await _run_merge(job)
    else:
        raise ValueError(f"unknown job kind: {job.kind}")


async def _run_e2e(job) -> None:
    p = job.params
    progress = JobProgress(job)
    progress.phase(f"e2e:{p['tier']}")
    await e2e_mod.run_e2e(p["tier"], p["dataset_size"], progress=progress)


async def _run_attack(job) -> None:
    p = job.params
    config = tiers.load_config()
    progress = JobProgress(job)

    progress.phase("attack")
    async with ServerStack(config, victim_tier=p["tier"]):
        model_name = config.get("model_name", "")
        gguf = tiers.resolve_gguf(p["tier"], config)
        victim = (
            await asyncio.to_thread(build_victim_block, p["tier"], gguf, model_name)
            if model_name
            else None
        )
        run_dir = runs.run_dir(p["run_name"]) if p.get("run_name") else None
        attack_task = asyncio.create_task(redteam.run_attacks(
            dataset_size=p["dataset_size"],
            objectives=p.get("objectives") or None,
            run_dir=run_dir,
            tier=p["tier"],
            victim=victim,
            progress=progress,
        ))
        poller = asyncio.create_task(_poll_attack_progress(job, attack_task))
        try:
            run_name = await attack_task
        finally:
            poller.cancel()

        if job.run_name is None:
            job.run_name = run_name
            job.emit({"type": "run", "run_name": run_name})

        progress.phase("extract")
        run_dir = runs.run_dir(run_name)
        responses = load_raw_responses(run_dir)
        scoring.score_pyrit_outcomes(responses, run_dir, None, progress)

    progress.phase("summary")
    await _summarize_run(run_dir)


async def _run_rescore(job) -> None:
    p = job.params
    run_dir = runs.run_dir(p["run_name"])
    progress = JobProgress(job)
    config = tiers.load_config()

    conversation_ids = set(p["conversation_ids"]) if p.get("conversation_ids") else None
    if conversation_ids:
        progress.phase("invalidate")
        for scored in sorted(runs.run_path(p["run_name"]).glob("scored_*.csv")):
            if scoring.load_scored_ids(scored) & conversation_ids:
                backup_file(scored)
        scoring.invalidate_scores(run_dir, conversation_ids)

    needs = {SCORER_SPECS[m]["model"] for m in p["models"] if m in SCORER_SPECS}
    victim_tier = None
    if "victim-llama" in needs:
        meta = read_meta(run_dir)
        victim_tier = p.get("tier") or meta.get("tier") or (meta.get("victim") or {}).get("tier")
        victim_tier = str(victim_tier).upper()

    progress.phase("scoring")
    update_meta(run_dir, status="scoring")
    async with ServerStack(config, victim_tier=victim_tier, bf16="bf16-llama" in needs):
        await scoring.run_scoring(run_dir, p["models"], conversation_ids=conversation_ids,
                                  progress=progress)
    update_meta(run_dir, status="complete")


async def _run_summarize(job) -> None:
    p = job.params
    progress = JobProgress(job)
    progress.phase("summary")
    await _summarize_run(runs.run_dir(p["run_name"]))


async def _run_merge(job) -> None:
    p = job.params
    from merge_runs import merge_runs as do_merge

    progress = JobProgress(job)
    progress.phase("merge")
    target = RESULTS_DIR / p["target"]
    sources = [RESULTS_DIR / s for s in p["sources"]]
    await asyncio.to_thread(do_merge, target, sources)
