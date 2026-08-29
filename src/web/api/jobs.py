"""Job submission, monitoring, and SSE live events."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.web import jobspec
from src.web.auth import require_token

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_token)], tags=["jobs"])


def _manager(request: Request):
    return request.app.state.jobs


class JobSpec(BaseModel):
    kind: str
    params: dict = {}


@router.post("")
def submit_job(spec: JobSpec, request: Request) -> dict:
    try:
        params, run_name = jobspec.validate_job(spec.kind, spec.params)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e
    job = _manager(request).submit(spec.kind, params, run_name)
    return job.record()


@router.get("")
def list_jobs(request: Request) -> dict:
    return {"jobs": _manager(request).list_records()}


@router.get("/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = _manager(request).get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")
    rec = job.record()
    rec["recent_events"] = [e for _, e in job.events[-50:]]
    return rec


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict:
    ok = await _manager(request).cancel(job_id)
    if not ok:
        raise HTTPException(400, f"job {job_id} cannot be cancelled (unknown or finished)")
    return {"cancelled": job_id}


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request):
    """SSE stream of job events (log lines, progress, status changes)."""
    manager = _manager(request)
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, f"job not found: {job_id}")

    last_event_id = request.headers.get("Last-Event-ID")
    try:
        last_seq = int(last_event_id) if last_event_id else 0
    except ValueError:
        last_seq = 0

    async def gen():
        q = job.subscribe(last_seq)
        try:
            if job.status in ("done", "error", "cancelled"):
                for _, event in job.events:
                    yield {"id": str(event["seq"]), "data": json.dumps(event)}
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    yield {"comment": "keep-alive"}
                    continue
                yield {"id": str(event["seq"]), "data": json.dumps(event)}
                if event.get("type") == "status" and event.get("status") in ("done", "error", "cancelled"):
                    break
        finally:
            job.unsubscribe(q)

    return EventSourceResponse(gen())
