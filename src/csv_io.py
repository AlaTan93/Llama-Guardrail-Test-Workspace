"""Shared CSV read / write helpers.

Replaces duplicate copies of the same logic that previously lived in
``redteam.py``, ``scoring.py``, and ``merge_runs.py``.
"""

import csv
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
