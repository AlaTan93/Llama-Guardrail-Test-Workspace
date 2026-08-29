"""Run inspection endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.web import runs, views
from src.web.auth import require_token

router = APIRouter(prefix="/runs", dependencies=[Depends(require_token)], tags=["runs"])


@router.get("")
def list_runs() -> dict:
    return {"runs": runs.list_runs()}


@router.get("/{run_name}")
def get_run(run_name: str) -> dict:
    try:
        return runs.run_overview(run_name)
    except FileNotFoundError:
        raise HTTPException(404, f"run not found: {run_name}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{run_name}/prompts")
def get_prompts(
    run_name: str,
    filter: str | None = None,
    q: str | None = None,
    scorer: str | None = None,
    value: str | None = None,
    quadrant: str | None = None,
) -> dict:
    if filter and filter not in ("errors", "undetermined", "cpv", "disagreement"):
        raise HTTPException(400, f"invalid filter: {filter}")
    if quadrant and quadrant not in views.QUADRANTS:
        raise HTTPException(400, f"invalid quadrant: {quadrant}")
    try:
        rows, scorers = views.load_prompt_rows(run_name)
    except FileNotFoundError:
        raise HTTPException(404, f"run not found (or no raw_responses.csv): {run_name}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    rows = views.filter_prompt_rows(rows, filter, q, scorer, value, quadrant)
    return {"run": run_name, "count": len(rows), "scorers": scorers, "rows": rows}


class MetaPatch(BaseModel):
    tier: str | None = None
    notes: str | None = None
    dataset_size: int | None = None


@router.patch("/{run_name}/meta")
def patch_meta(run_name: str, patch: MetaPatch) -> dict:
    try:
        runs.run_path(run_name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not runs.run_exists(run_name):
        raise HTTPException(404, f"run not found: {run_name}")
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "empty patch")
    from src.run_meta import update_meta

    meta = update_meta(str(runs.run_path(run_name)), **fields)
    return {"meta": meta}
