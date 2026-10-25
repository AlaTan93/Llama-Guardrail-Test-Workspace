"""FastAPI app factory: routers + static SPA + startup."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import routes_runs, routes_system
from app.db import init_db
from app.pyrit.lifecycle import ensure_pyrit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("harness")

app = FastAPI(title="Guardrail Testing Stack v2", version="0.1.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


@app.on_event("startup")
async def startup() -> None:
    await init_db()
    await ensure_pyrit()


app.include_router(routes_system.router, prefix="/api")
app.include_router(routes_runs.router, prefix="/api")

if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
else:
    logger.warning("static SPA directory missing at %s; API-only mode", STATIC_DIR)
