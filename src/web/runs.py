"""Run directory access: discovery, validation, listing, overview.

The single authority on run names/paths (blocks path traversal) and on
reading a run's files as structured data.  Derived analysis views (per-prompt
joins, comparisons) live in :mod:`src.web.views`.
"""

import re
from pathlib import Path

from src.config import RESULTS_DIR
from src.csv_io import load_csv
from src.run_meta import read_meta
from src.scorers import DEFAULT_MODELS

_RUN_NAME_RE = re.compile(r"^run_[A-Za-z0-9._-]+$")

SUMMARY_FILES = {
    "asr": "summary.csv",
    "refusal": "summary_refusal.csv",
    "crosstab": "summary_crosstab.csv",
}


def run_path(run_name: str) -> Path:
    """Validated path for *run_name* (blocks path traversal)."""
    if not _RUN_NAME_RE.match(run_name):
        raise ValueError(f"invalid run name: {run_name!r}")
    p = (RESULTS_DIR / run_name).resolve()
    if p.parent != RESULTS_DIR.resolve():
        raise ValueError(f"invalid run name: {run_name!r}")
    return p


def run_dir(run_name: str) -> str:
    """``results/<run_name>`` as a string (convenience for pipeline calls)."""
    return str(RESULTS_DIR / run_name)


def run_exists(run_name: str) -> bool:
    try:
        return run_path(run_name).is_dir()
    except ValueError:
        return False


def scorers_in_run(run_dir_path: Path) -> list[str]:
    return sorted(p.stem.removeprefix("scored_") for p in run_dir_path.glob("scored_*.csv"))


def _derived_status(run_dir_path: Path) -> str:
    if not (run_dir_path / "raw_responses.csv").exists():
        return "empty"
    scorers = scorers_in_run(run_dir_path)
    if set(DEFAULT_MODELS) <= set(scorers):
        return "complete"
    if scorers:
        return "partial"
    return "new"


def list_runs() -> list[dict]:
    out = []
    for d in sorted(RESULTS_DIR.glob("run_*"), reverse=True):
        if not d.is_dir():
            continue
        meta = read_meta(d)
        raw = load_csv(d / "raw_responses.csv")
        scored_counts = {
            p.stem.removeprefix("scored_"): sum(1 for _ in open(p, encoding="utf-8")) - 1
            for p in sorted(d.glob("scored_*.csv"))
        }
        has_summary = {k: (d / f).exists() for k, f in SUMMARY_FILES.items()}
        out.append({
            "name": d.name,
            "tier": meta.get("tier") or "",
            "victim_model": (meta.get("victim") or {}).get("model", ""),
            "status": _derived_status(d),
            "dataset_size": meta.get("dataset_size") or len(raw),
            "created_at": meta.get("created_at") or "",
            "raw_count": len(raw),
            "scored_counts": scored_counts,
            "summaries": has_summary,
            "notes": meta.get("notes", ""),
        })
    return out


def run_overview(run_name: str) -> dict:
    d = run_path(run_name)
    if not d.is_dir():
        raise FileNotFoundError(run_name)
    meta = read_meta(d)
    raw = load_csv(d / "raw_responses.csv")
    scorers = scorers_in_run(d)
    summaries = {}
    for key, fname in SUMMARY_FILES.items():
        rows = load_csv(d / fname)
        summaries[key] = {"present": bool(rows), "rows": rows}
    return {
        "name": run_name,
        "meta": meta,
        "status": _derived_status(d),
        "raw_count": len(raw),
        "scorers": scorers,
        "summaries": summaries,
        "backups": sorted(p.name for p in (d / "backups").glob("*.csv")) if (d / "backups").is_dir() else [],
    }
