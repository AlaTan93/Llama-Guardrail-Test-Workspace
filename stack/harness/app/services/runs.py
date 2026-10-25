"""Run queries and the RunManager.

The manager owns spawned worker tasks. Holding references matters: a bare
``asyncio.create_task`` result can be garbage-collected mid-run, silently
killing the worker. It also gives a single place to add cancellation later.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models import Objective, Run
from app.schemas import RunOut


async def create_run(**fields) -> Run:
    async with AsyncSessionLocal() as session:
        run = Run(**fields)
        session.add(run)
        await session.commit()
        return run


async def get_run(run_id: uuid.UUID) -> Run | None:
    async with AsyncSessionLocal() as session:
        return await session.get(Run, run_id)


async def list_runs() -> list[Run]:
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(Run).order_by(Run.created_at.desc()))).scalars().all()


async def count_objectives(run_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(select(func.count()).select_from(Objective).where(Objective.run_id == run_id))
        ).scalar_one()


async def run_out(run: Run) -> RunOut:
    """RunOut with progress counts (detached-safe: reads only column attrs)."""
    out = RunOut.model_validate(run)
    out.n_objectives = len(run.prompts)
    out.n_objectives_done = await count_objectives(run.id)
    return out


class RunManager:
    """Registry of in-flight run tasks."""

    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}

    def spawn(self, run_id: uuid.UUID) -> None:
        from app.services.worker import execute_run  # local import avoids a cycle

        task = asyncio.get_running_loop().create_task(execute_run(run_id), name=f"run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _t, rid=run_id: self._tasks.pop(rid, None))

    def cancel(self, run_id: uuid.UUID) -> bool:
        task = self._tasks.get(run_id)
        if task is None:
            return False
        task.cancel()
        return True

    @property
    def active(self) -> int:
        return len(self._tasks)


manager = RunManager()
