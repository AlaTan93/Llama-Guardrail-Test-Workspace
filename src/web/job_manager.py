"""Serialized job manager with SSE live updates.

One GPU job runs at a time (the host has a single GPU).  Jobs are asyncio
tasks on the server's event loop; ``print`` output from the pipeline is
captured via ``redirect_stdout`` and fanned out to SSE subscribers as log
events, alongside structured progress/status events.

State survives restarts via ``.webapp/jobs.json`` (job records) and
``.webapp/logs/<job_id>.log`` (full logs).
"""

import asyncio
import contextlib
import json
import threading
import time
import traceback
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from src.web.settings import JOBS_FILE, LOGS_DIR

JOB_KINDS = ("e2e", "attack", "rescore", "summarize", "merge")
TERMINAL = ("done", "error", "cancelled")

_EVENT_HISTORY = 500


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


class Job:
    def __init__(self, job_id: str, kind: str, params: dict, run_name: str | None = None):
        self.id = job_id
        self.kind = kind
        self.params = params
        self.run_name = run_name
        self.status = "queued"
        self.error: str | None = None
        self.created_at = _now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.progress: dict = {}
        self.task: asyncio.Task | None = None
        self.events: list[tuple[int, dict]] = []
        self._seq = 0
        self._emit_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: list[asyncio.Queue] = []
        self._log_file: Path | None = None
        self._log_fh = None

    # ── records (persisted) ──
    def record(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "params": self.params,
            "run_name": self.run_name,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": self.progress,
        }

    # ── events ──
    def emit(self, event: dict) -> None:
        """Thread-safe event emission (may be called from ``to_thread`` workers).

        Fan-out to subscriber queues is scheduled onto the bound event loop
        when emitted from a foreign thread.
        """
        with self._emit_lock:
            self._seq += 1
            event = {"seq": self._seq, "ts": time.time(), **event}
            self.events.append((self._seq, event))
            if len(self.events) > _EVENT_HISTORY:
                del self.events[:-_EVENT_HISTORY]
            if event.get("type") == "log" and self._log_fh:
                self._log_fh.write(event["line"] + "\n")
                self._log_fh.flush()

        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                loop.call_soon_threadsafe(self._fanout, event)
                return
        self._fanout(event)

    def _fanout(self, event: dict) -> None:
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, last_seq: int = 0) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        for seq, event in self.events:
            if seq > last_seq:
                q.put_nowait(event)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with contextlib.suppress(ValueError):
            self._subscribers.remove(q)

    def open_log(self) -> None:
        self._log_file = LOGS_DIR / f"{self.id}.log"
        self._log_fh = open(self._log_file, "a", encoding="utf-8")

    def close_log(self) -> None:
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None


class _TeeIO:
    """File-like stdout replacement that emits lines as job log events."""

    def __init__(self, job: Job):
        self.job = job
        self._buf = ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self.job.emit({"type": "log", "line": line})
        return len(text)

    def flush(self) -> None:
        if self._buf.strip():
            self.job.emit({"type": "log", "line": self._buf})
        self._buf = ""


class JobManager:
    def __init__(self):
        self.jobs: OrderedDict[str, Job] = OrderedDict()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._counter = 0
        self._stopping = False

    # ── lifecycle ──
    def start(self) -> None:
        self._load_records()
        self._worker = asyncio.get_running_loop().create_task(self._worker_loop())

    async def shutdown(self) -> None:
        self._stopping = True
        for job in self.jobs.values():
            if job.status == "running" and job.task:
                job.task.cancel()
            elif job.status == "queued":
                job.status = "error"
                job.error = "interrupted by server restart"
                job.finished_at = _now()
                job.close_log()
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
        for job in self.jobs.values():
            if job.status == "running":
                job.status = "error"
                job.error = "interrupted by server restart"
                job.finished_at = _now()
                job.close_log()
        self._save_records()

    # ── persistence ──
    def _load_records(self) -> None:
        if not JOBS_FILE.exists():
            return
        try:
            records = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for rec in records:
            job = Job(rec["id"], rec.get("kind", "?"), rec.get("params", {}), rec.get("run_name"))
            job.status = rec.get("status", "error")
            if job.status in ("queued", "running"):
                job.status = "error"
                job.error = "interrupted by server restart"
            job.error = rec.get("error")
            job.created_at = rec.get("created_at", job.created_at)
            job.started_at = rec.get("started_at")
            job.finished_at = rec.get("finished_at")
            job.progress = rec.get("progress", {})
            self.jobs[job.id] = job
            self._counter = max(self._counter, int(job.id.rsplit("_", 1)[-1]))

    def _save_records(self) -> None:
        records = [j.record() for j in self.jobs.values()][-500:]
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        JOBS_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # ── API ──
    def submit(self, kind: str, params: dict, run_name: str | None = None) -> Job:
        if kind not in JOB_KINDS:
            raise ValueError(f"unknown job kind: {kind}")
        self._counter += 1
        job_id = f"job_{int(time.time())}_{self._counter}"
        job = Job(job_id, kind, params, run_name)
        self.jobs[job_id] = job
        job.emit({"type": "status", "status": "queued"})
        self._queue.put_nowait(job_id)
        self._save_records()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list_records(self) -> list[dict]:
        return [j.record() for j in reversed(self.jobs.values())]

    def current(self) -> Job | None:
        for j in self.jobs.values():
            if j.status == "running":
                return j
        return None

    async def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None or job.status not in ("queued", "running"):
            return False
        if job.status == "queued":
            job.status = "cancelled"
            job.finished_at = _now()
            job.emit({"type": "status", "status": "cancelled"})
            self._save_records()
            return True
        if job.task:
            job.task.cancel()
        return True

    # ── worker ──
    async def _worker_loop(self) -> None:
        while not self._stopping:
            job_id = await self._queue.get()
            job = self.jobs.get(job_id)
            if job is None or job.status != "queued":
                continue
            await self._execute(job)

    async def _execute(self, job: Job) -> None:
        job.status = "running"
        job.started_at = _now()
        job.bind_loop(asyncio.get_running_loop())
        job.open_log()
        job.emit({"type": "status", "status": "running"})
        self._save_records()

        job.task = asyncio.create_task(self._run_with_capture(job))
        try:
            await job.task
        except asyncio.CancelledError:
            if self._stopping:
                raise  # server shutdown: let the worker die

        job.finished_at = _now()
        job.progress = {}
        job.close_log()
        self._save_records()

    async def _run_with_capture(self, job: Job) -> None:
        import sys

        from src.web import runners

        tee = _TeeIO(job)
        try:
            with contextlib.redirect_stdout(tee):
                await runners.run_job(job)
            job.status = "done"
            job.emit({"type": "status", "status": "done"})
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.emit({"type": "status", "status": "cancelled"})
            raise
        except BaseException:
            job.status = "error"
            job.error = traceback.format_exc(limit=8)
            job.emit({"type": "status", "status": "error", "error": job.error})
            sys.stderr.write(job.error + "\n")
        finally:
            tee.flush()
