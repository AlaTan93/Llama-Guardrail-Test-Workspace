"""Centralised paths, service hosts, and CSV schemas.

Scorer definitions live in :mod:`src.scorers`; tier resolution in
:mod:`src.tiers`.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"

LITELLM_PORT = 4000


def _host(env_var: str) -> str:
    """Service hostname from env (container networking), default localhost."""
    return os.environ.get(env_var, "127.0.0.1")


VICTIM_HOST = _host("VICTIM_HOST")
BF16_HOST = _host("BF16_HOST")
LITELLM_HOST = _host("LITELLM_HOST")

LITELLM_ENDPOINT = f"http://{LITELLM_HOST}:{LITELLM_PORT}/v1"

# ── CSV field definitions ──────────────────────────────────────────

RAW_FIELDS = [
    "objective", "last_response", "strategy", "conversation_id",
    "executed_turns", "execution_time_ms", "pyrit_outcome", "pyrit_outcome_reason",
]

SCORED_FIELDS = [
    "objective", "last_response", "strategy", "conversation_id",
    "score_value", "score_rationale", "scorer_type",
    "executed_turns", "execution_time_ms",
]
