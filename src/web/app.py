"""FastAPI application factory for the web dashboard.

Run with::

    uv run uvicorn src.web.app:app --host 0.0.0.0 --port 8000

Auth: every ``/api`` route requires ``Authorization: Bearer <token>``
(the token prints at startup; override with ``WEB_TOKEN`` in ``.env``).
The SSE endpoint also accepts ``?token=`` because ``EventSource`` cannot
send headers.

Serves the built SPA from ``frontend/dist`` when present.
"""

import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.web import settings
from src.web.api import compare, jobs, runs, system
from src.web.auth import require_token
from src.web.job_manager import JobManager

DIST_DIR = settings.PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.load_env_file()
    settings.ensure_state_dirs()
    app.state.web_token = settings.get_web_token()
    manager = JobManager()
    app.state.jobs = manager
    manager.start()

    host_note = "0.0.0.0:8000 (LAN reachable)"
    print("=" * 60, file=sys.stderr)
    print("Web dashboard token:", app.state.web_token, file=sys.stderr)
    print("Serving on:", host_note, file=sys.stderr)
    if not DIST_DIR.exists():
        print("frontend/dist not found — run scripts/build_frontend.sh", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    yield
    await manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Quantization Red-Team Dashboard", lifespan=lifespan)

    app.include_router(runs.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(compare.router, prefix="/api")
    app.include_router(system.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/whoami")
    def whoami(_: None = Depends(require_token)) -> dict:
        return {"ok": True}

    if DIST_DIR.exists():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str) -> FileResponse:
            candidate = (DIST_DIR / full_path).resolve()
            if str(candidate).startswith(str(DIST_DIR.resolve())) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(DIST_DIR / "index.html")

    else:
        @app.get("/{full_path:path}")
        def fallback(full_path: str) -> JSONResponse:
            return JSONResponse(
                {"detail": "frontend not built — run scripts/build_frontend.sh"},
                status_code=404,
            )

    return app


app = create_app()
