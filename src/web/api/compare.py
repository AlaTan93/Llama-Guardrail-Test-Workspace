"""Cross-run comparison endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from src.web import views
from src.web.auth import require_token

router = APIRouter(prefix="/compare", dependencies=[Depends(require_token)], tags=["compare"])


@router.get("")
def compare(kind: str = "asr", runs: str = "") -> dict:
    if kind not in views.SUMMARY_FILES:
        raise HTTPException(400, f"invalid kind: {kind} (asr|refusal|crosstab)") from None
    run_names = [r.strip() for r in runs.split(",") if r.strip()]
    if not run_names:
        raise HTTPException(400, "runs query parameter required (comma-separated)")
    try:
        return views.compare_summaries(run_names, kind)
    except FileNotFoundError as e:
        raise HTTPException(404, f"run not found: {e}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/prompts")
def compare_prompts(runs: str = "") -> dict:
    run_names = [r.strip() for r in runs.split(",") if r.strip()]
    if not run_names:
        raise HTTPException(400, "runs query parameter required (comma-separated)")
    try:
        return views.compare_prompts(run_names)
    except FileNotFoundError as e:
        raise HTTPException(404, f"run not found: {e}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
