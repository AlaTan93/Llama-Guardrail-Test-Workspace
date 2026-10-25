"""Shared API dependencies."""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.services.runs import get_run


def parse_run_id(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid run id") from exc


async def get_run_or_404(run_id: str):
    run = await get_run(parse_run_id(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
