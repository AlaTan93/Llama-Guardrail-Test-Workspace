"""Shared CSV read / write helpers.

Replaces duplicate copies of the same logic that previously lived in
``redteam.py``, ``scoring.py``, and ``merge_runs.py``.
"""

import csv
import shutil
from datetime import UTC
from pathlib import Path

from src.config import SCORED_FIELDS


def load_csv(path: Path) -> list[dict]:
    """Return all rows from *path* as a list of dicts. Empty list if absent."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    """Write *rows* to *path* using *fields* as the column order."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_raw_responses(run_dir: str) -> list[dict]:
    """Load ``raw_responses.csv`` from *run_dir*. Raises if not found."""
    path = Path(run_dir) / "raw_responses.csv"
    if not path.exists():
        raise FileNotFoundError(f"raw_responses.csv not found in {run_dir}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_scored_ids(path: Path) -> set[str]:
    """Return the set of conversation_ids already present in *path*."""
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {
            row["conversation_id"]
            for row in csv.DictReader(f)
            if row.get("conversation_id")
        }


def append_scored_row(path: Path, row: dict, write_header: bool) -> None:
    """Append a single scored row to *path*, writing the header first if requested."""
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCORED_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ── Row surgery (partial reruns) ───────────────────────────────────

def count_rows(path: Path) -> int:
    """Number of data rows in a CSV (0 if absent)."""
    return len(load_csv(path))


def _drop_rows(path: Path, keep) -> tuple[int, list[dict]]:
    """Rewrite *path* keeping rows for which ``keep(row)`` is True.

    Returns ``(dropped_count, kept_rows)``.  No-op if *path* is absent.
    """
    if not path.exists():
        return 0, []
    rows = load_csv(path)
    kept = [r for r in rows if keep(r)]
    dropped = len(rows) - len(kept)
    if dropped:
        fields = list(rows[0].keys()) if rows else SCORED_FIELDS
        tmp = path.with_suffix(path.suffix + ".tmp")
        write_csv(tmp, kept, fields)
        tmp.replace(path)
    return dropped, kept


def drop_scored_rows(path: Path, conversation_ids: set[str]) -> int:
    """Remove rows for *conversation_ids* from a scored CSV.  Returns count dropped."""
    dropped, _ = _drop_rows(path, lambda r: r.get("conversation_id") not in conversation_ids)
    return dropped


def drop_raw_rows(path: Path, objectives: set[str]) -> tuple[int, set[str]]:
    """Remove rows matching *objectives* from raw_responses.csv.

    Returns ``(dropped_count, dropped_conversation_ids)`` so callers can
    invalidate the corresponding scored rows.
    """
    if not path.exists():
        return 0, set()
    rows = load_csv(path)
    dropped_ids = {r["conversation_id"] for r in rows if r.get("objective") in objectives}
    dropped, _ = _drop_rows(path, lambda r: r.get("objective") not in objectives)
    return dropped, dropped_ids


def backup_file(path: Path, backup_dir: Path | None = None) -> Path | None:
    """Copy *path* to ``<run>/backups/<stem>_<timestamp>.csv``.  None if absent."""
    if not path.exists():
        return None
    from datetime import datetime

    ts = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S%f")[:-3]
    backup_dir = backup_dir or (path.parent / "backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{path.stem}_{ts}{path.suffix}"
    shutil.copy2(path, dest)
    return dest
