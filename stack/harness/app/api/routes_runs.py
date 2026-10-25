"""Run routes: create, list/detail, objectives, stats, SSE progress."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_run_or_404
from app.schemas import ObjectiveOut, RunCreate, RunOut, RunStats
from app.services.analytics import compute_stats
from app.services.runs import create_run, list_runs, manager, run_out
from app.services.worker import TERMINAL_STATUSES, run_objectives
from app.config import settings

router = APIRouter()


@router.post("/runs", response_model=RunOut, status_code=201)
async def create_run_route(body: RunCreate) -> RunOut:
    judges = body.judges or settings.judge_aliases
    primary = body.primary_judge or settings.primary_judge
    if primary not in judges:
        raise HTTPException(status_code=400, detail=f"primary judge {primary!r} must be in judges {judges!r}")

    prompts = [p.strip() for p in body.prompts if p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="at least one non-empty prompt is required")

    run = await create_run(
        prompts=prompts,
        target_alias=body.target_alias or settings.target_alias,
        judges=judges,
        primary_judge=primary,
        concurrency=body.concurrency,
        labels=body.labels,
        guardrail_config=body.guardrail_config,
    )
    manager.spawn(run.id)
    return await run_out(run)


@router.get("/runs", response_model=list[RunOut])
async def list_runs_route() -> list[RunOut]:
    return [await run_out(run) for run in await list_runs()]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run_route(run_id: str) -> RunOut:
    return await run_out(await get_run_or_404(run_id))


@router.get("/runs/{run_id}/objectives", response_model=list[ObjectiveOut])
async def get_objectives_route(run_id: str) -> list[ObjectiveOut]:
    run = await get_run_or_404(run_id)
    return [ObjectiveOut.model_validate(obj) for obj in await run_objectives(run.id)]


@router.get("/runs/{run_id}/stats", response_model=RunStats)
async def get_stats_route(run_id: str) -> RunStats:
    run = await get_run_or_404(run_id)
    return compute_stats(run, await run_objectives(run.id))


@router.get("/runs/{run_id}/events")
async def run_events_route(run_id: str) -> StreamingResponse:
    """SSE: pushes run status + progress counts until the run terminates."""
    await get_run_or_404(run_id)

    async def stream() -> AsyncIterator[bytes]:
        last_payload = None
        while True:
            run = await get_run_or_404(run_id)
            payload = (await run_out(run)).model_dump(mode="json")
            if payload != last_payload:
                last_payload = payload
                yield f"event: run\ndata: {json.dumps(payload)}\n\n".encode()
            if run.status in TERMINAL_STATUSES:
                yield b"event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(1.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
