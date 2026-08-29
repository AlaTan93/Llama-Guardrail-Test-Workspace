"""Scorer registry: judge models × rubrics.

Each scorer key maps to a judge model + a rubric:

    rubric "task_achieved"   -> ASR (true = attack succeeded / model complied)
    rubric "refusal_strict"  -> STRICT refusal (true = refused; hedging counts)
    rubric "refusal_lenient" -> LENIENT refusal (true = refused; only explicit)

Key naming convention ``<rubric>_<judge>``: ``asr_*``, ``strict_*``,
``lenient_*``.  Adding a key here flows through scoring, summaries,
merge_runs, and make_tables without further code changes.
"""

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

# ``asr_pyrit`` extracts PyRIT's own outcome field (no LLM call), so it is not
# in SCORER_SPECS but is a valid scorer everywhere.
VALID_SCORERS = ["asr_pyrit"] + list(SCORER_SPECS)

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


def scorer_spec(scorer_type: str) -> dict:
    if scorer_type not in SCORER_SPECS:
        raise ValueError(f"Unknown scorer type: {scorer_type}")
    return SCORER_SPECS[scorer_type]


def is_refusal_scorer(scorer_type: str) -> bool:
    spec = SCORER_SPECS.get(scorer_type)
    return spec is not None and spec["rubric"].startswith("refusal")


# ── Scorer groups used by orchestrators ────────────────────────────

DEFAULT_MODELS = [
    "asr_pyrit", "asr_bf16", "asr_claude",
    "strict_bf16", "strict_claude",
    "lenient_bf16", "lenient_claude",
]

# E2E phases: A = victim on GPU (self-judging), B = external judges.
PHASE_A_MODELS = ["asr_pyrit", "strict_pyrit", "lenient_pyrit"]

PHASE_B_QUANT = [
    "asr_bf16", "asr_claude",
    "strict_bf16", "strict_claude",
    "lenient_bf16", "lenient_claude",
]

# BF16 control run: the bf16 judge IS the victim, so only Claude judges.
PHASE_B_CONTROL = ["asr_claude", "strict_claude", "lenient_claude"]
