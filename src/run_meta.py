"""Per-run metadata (``meta.json``) for the web layer and CLI.

Each run directory under ``results/`` may carry a ``meta.json`` describing
the run (tier, dataset size, status, notes).  Runs created before this
module existed simply have no file; :func:`read_meta` returns defaults.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

META_FILENAME = "meta.json"

VALID_STATUSES = {"new", "attack_running", "scoring", "complete", "error"}

META_FIELDS = [
    "tier", "dataset_size", "victim", "strategies",
    "created_at", "updated_at", "status", "notes",
]


def meta_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / META_FILENAME


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def default_meta() -> dict:
    return {
        "tier": "",
        "dataset_size": None,
        "victim": {},
        "strategies": [],
        "created_at": "",
        "updated_at": "",
        "status": "new",
        "notes": "",
    }


def read_meta(run_dir: str | Path) -> dict:
    """Read ``meta.json`` from *run_dir*, filling defaults for missing fields."""
    meta = default_meta()
    path = meta_path(run_dir)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for k in META_FIELDS:
                    if k in stored and stored[k] is not None:
                        meta[k] = stored[k]
        except (json.JSONDecodeError, OSError):
            pass
    return meta


def write_meta(run_dir: str | Path, meta: dict) -> Path:
    """Write *meta* (full replace) to ``meta.json``."""
    path = meta_path(run_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    return path


def update_meta(run_dir: str | Path, **fields) -> dict:
    """Read-modify-write ``meta.json``; unknown keys are ignored.

    ``updated_at`` is always refreshed; ``created_at`` is set on first write.
    """
    meta = read_meta(run_dir)
    for k, v in fields.items():
        if k in META_FIELDS:
            meta[k] = v
    if not meta["created_at"]:
        meta["created_at"] = now_iso()
    meta["updated_at"] = now_iso()
    write_meta(run_dir, meta)
    return meta
