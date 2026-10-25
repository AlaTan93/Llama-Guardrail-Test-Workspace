"""System routes: health + live LiteLLM model aliases."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app import litellm
from app.config import settings
from app.db import AsyncSessionLocal

logger = logging.getLogger("harness.api")
router = APIRouter()


@router.get("/health")
async def health() -> dict:
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("db health check failed: %r", exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "litellm": await litellm.reachable(),
        "target_alias": settings.target_alias,
        "judges": settings.judge_aliases,
        "primary_judge": settings.primary_judge,
    }


@router.get("/models")
async def models() -> dict:
    """Registered LiteLLM aliases (live from the proxy) for the SPA form."""
    try:
        return {"aliases": await litellm.aliases()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"litellm unreachable: {exc!r}") from exc
