"""Run persistence: writing and merging ``results/run_*`` artifacts.

Owns everything that touches a run directory's files on behalf of the attack
phase: raw response rows from a PyRIT ``ScenarioResult``, ``meta.json``
bookkeeping, and the in-place replace semantics of re-attacks (backups →
drop old rows → invalidate their scores → append new rows).
"""

import os
from datetime import UTC, datetime
from pathlib import Path

from pyrit.scenario import ScenarioResult

from src.config import RAW_FIELDS, RESULTS_DIR
from src.csv_io import backup_file, drop_raw_rows, drop_scored_rows, load_csv, write_csv
from src.run_meta import update_meta, write_meta


def rows_from_scenario(scenario_result: ScenarioResult) -> list[dict]:
    """Flatten a PyRIT ScenarioResult into raw_responses row dicts."""
    raw_rows: list[dict] = []
    for strategy, results in scenario_result.attack_results.items():
        for r in results:
            raw_rows.append({
                "objective": r.objective,
                "last_response": r.last_response.original_value if r.last_response else "",
                "strategy": strategy,
                "conversation_id": r.conversation_id,
                "executed_turns": r.executed_turns,
                "execution_time_ms": r.execution_time_ms,
                "pyrit_outcome": r.outcome.value,
                "pyrit_outcome_reason": r.outcome_reason or "",
            })
    return raw_rows


def write_new_run(
    raw_rows: list[dict],
    *,
    tier: str | None,
    dataset_size: int | None,
    victim_model_name: str,
    victim: dict | None,
) -> str:
    """Create a fresh ``run_<timestamp>`` directory with raw rows + meta."""
    now = datetime.now(tz=UTC)
    ts = now.strftime("%Y%m%d%H%M%S") + now.strftime("%f")[:3]
    run_name = f"run_{ts}"

    results_dir = RESULTS_DIR / run_name
    os.makedirs(results_dir, exist_ok=True)

    write_csv(results_dir / "raw_responses.csv", raw_rows, RAW_FIELDS)
    strategies = sorted({r["strategy"] for r in raw_rows})
    write_meta(results_dir, {
        **({"tier": tier} if tier else {}),
        "dataset_size": dataset_size if dataset_size is not None else len(raw_rows),
        "victim": victim if victim is not None else {"litellm_model": victim_model_name},
        "strategies": strategies,
        "created_at": now.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"),
        "status": "new",
    })
    print(f"Results written to {results_dir}")
    return run_name


def merge_into_run(new_rows: list[dict], run_dir: str, victim: dict | None) -> dict:
    """Re-attack merge: replace rows for the attacked objectives in *run_dir*.

    Backs up ``raw_responses.csv`` and every affected scored CSV first, then:
      1. drops old raw rows for those objectives,
      2. invalidates their conversation_ids from all scored files,
      3. appends the new raw rows,
      4. refreshes the victim provenance block (tier may differ).
    """
    raw_path = Path(run_dir) / "raw_responses.csv"

    objectives = {r["objective"] for r in new_rows}

    backup_file(raw_path)

    dropped_raw, dropped_ids = drop_raw_rows(raw_path, objectives)
    for scored in Path(run_dir).glob("scored_*.csv"):
        backup_file(scored)
        drop_scored_rows(scored, dropped_ids)

    existing = load_csv(raw_path)
    write_csv(raw_path, existing + new_rows, RAW_FIELDS)

    meta_fields: dict = {"status": "new"}
    if victim is not None:
        meta_fields.update({"victim": victim, "tier": victim.get("tier", "")})
    update_meta(run_dir, **meta_fields)

    print(f"Merged {len(new_rows)} re-attacked rows into {run_dir} "
          f"(replaced {dropped_raw} old rows, invalidated {len(dropped_ids)} scored ids)")
    return {"added": len(new_rows), "replaced": dropped_raw, "invalidated": len(dropped_ids)}
