"""Victim model provenance for runs.

Builds the ``victim`` block stored in each run's ``meta.json``:

    {
      "model":          "meta-llama/Llama-3.1-8B-Instruct",
      "tier":           "Q4_K_M",
      "gguf":           "meta-llama-…-Q4_K_M.gguf",
      "gguf_size_mb":   4921.7,
      "gguf_sha256":    "ab12…",      # cached, one hash per file
      "litellm_model":  "victim-llama"
    }

SHA-256 hashing a multi-GB GGUF takes tens of seconds, so results are cached
in ``.webapp/gguf_hashes.json`` keyed by absolute path and invalidated when
the file's size or mtime changes.  Callers on an event loop should invoke
``build_victim_block`` via ``asyncio.to_thread``.
"""

import hashlib
import json
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = PROJECT_ROOT / ".webapp" / "gguf_hashes.json"

_lock = threading.Lock()


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def sha256_cached(path: Path | str) -> str:
    """SHA-256 of *path*, cached by (size, mtime)."""
    p = Path(path)
    st = p.stat()
    key = str(p.resolve())

    with _lock:
        entry = _load_cache().get(key)
        if entry and entry.get("size") == st.st_size and entry.get("mtime") == st.st_mtime:
            return entry["sha256"]

    print(f"Hashing {p.name} ({st.st_size / 1e9:.1f} GB) …")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()

    with _lock:
        cache = _load_cache()
        cache[key] = {"size": st.st_size, "mtime": st.st_mtime, "sha256": digest}
        _save_cache(cache)
    return digest


def build_victim_block(
    tier: str,
    gguf_path: Path | str,
    model_name: str,
    litellm_model: str = "victim-llama",
    with_hash: bool = True,
) -> dict:
    """Build the victim provenance block for a run.

    *model_name* comes from ``model_name`` in ``src/e2e_config.yaml``.
    """
    p = Path(gguf_path)
    return {
        "model": model_name,
        "tier": tier,
        "gguf": p.name,
        "gguf_size_mb": round(p.stat().st_size / 1e6, 1),
        "gguf_sha256": sha256_cached(p) if with_hash else "",
        "litellm_model": litellm_model,
    }
