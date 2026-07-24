"""Centralised constants for the pipeline.

All paths, scorer definitions, field lists, and default model groups live here
so that no other module re-declares them.
"""

from pathlib import Path

import src.litellm_proxy as litellm_proxy

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"

LITELLM_ENDPOINT = f"http://127.0.0.1:{litellm_proxy.LITELLM_PORT}/v1"

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

# ── Scorer definitions ─────────────────────────────────────────────
#
# Each scorer key maps to a judge model + a rubric.
#   rubric "task_achieved"   -> ASR (true = attack succeeded / model complied)
#   rubric "refusal_strict"  -> STRICT refusal (true = refused; hedging counts)
#   rubric "refusal_lenient" -> LENIENT refusal (true = refused; only explicit)
# Key naming convention:  <rubric>_<judge>
#   asr_*     — ASR scorers (task_achieved)
#   strict_*  — STRICT refusal scorers
#   lenient_* — LENIENT refusal scorers
# Adding a key here automatically flows through scoring, summaries, merge_runs,
# and make_tables without further code changes.

SCORER_SPECS = {
    "asr_bf16":        {"model": "bf16-llama",       "rubric": "task_achieved"},
    "asr_claude":      {"model": "claude-haiku-4.5", "rubric": "task_achieved"},
    "strict_claude":   {"model": "claude-haiku-4.5", "rubric": "refusal_strict"},
    "strict_bf16":     {"model": "bf16-llama",       "rubric": "refusal_strict"},
    "strict_pyrit":    {"model": "victim-llama",     "rubric": "refusal_strict"},
    "lenient_claude":  {"model": "claude-haiku-4.5", "rubric": "refusal_lenient"},
    "lenient_bf16":    {"model": "bf16-llama",       "rubric": "refusal_lenient"},
    "lenient_pyrit":   {"model": "victim-llama",     "rubric": "refusal_lenient"},
}

# Maps each refusal scorer (strict or lenient) to its ASR counterpart (same
# judge model) so the capability-gap and crosstab metrics can pair compliance
# with attack success.
REFUSAL_ASR_COUNTERPART = {
    "strict_claude":   "asr_claude",
    "strict_bf16":     "asr_bf16",
    "strict_pyrit":    "asr_pyrit",
    "lenient_claude":  "asr_claude",
    "lenient_bf16":    "asr_bf16",
    "lenient_pyrit":   "asr_pyrit",
}

# ── Default model groups ───────────────────────────────────────────

DEFAULT_MODELS = [
    "asr_pyrit", "asr_bf16", "asr_claude",
    "strict_bf16", "strict_claude",
    "lenient_bf16", "lenient_claude",
]

# ── E2E phase model groups ─────────────────────────────────────────

PHASE_A_MODELS = ["asr_pyrit", "strict_pyrit", "lenient_pyrit"]

PHASE_B_QUANT = [
    "asr_bf16", "asr_claude",
    "strict_bf16", "strict_claude",
    "lenient_bf16", "lenient_claude",
]

PHASE_B_CONTROL = ["asr_claude", "strict_claude", "lenient_claude"]
