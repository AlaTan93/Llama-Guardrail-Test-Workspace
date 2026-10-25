"""Run-level analytics: per-judge rates, inter-judge agreement, self-divergence.

All computed in Python from Postgres rows; undetermined scores are reported
as their own bucket and never silently counted as success/failure.
"""

from __future__ import annotations

from itertools import combinations

from app.models import Objective, Run
from app.schemas import (
    DivergenceAttack,
    DivergenceRefusal,
    JudgeStats,
    KindStats,
    PairAgreement,
    RunStats,
    SelfDivergence,
)

ATTACK_SUCCESS = "attack_success"
REFUSAL = "refusal"


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 2) if denominator else None


def _kind_stats(scores: list, kind: str) -> KindStats:
    rows = [s for s in scores if s.scorer_kind == kind]
    complete = [s for s in rows if s.status == "complete" and s.value_bool is not None]
    true_n = sum(1 for s in complete if s.value_bool is True)
    return KindStats(
        total=len(rows),
        true=true_n,
        false=len(complete) - true_n,
        undetermined=len(rows) - len(complete),
        rate_pct=_pct(true_n, len(complete)),
    )


def _verdict(objective: Objective, kind: str, judge: str) -> bool | None:
    """Complete verdict for one cell, or None if absent/undetermined."""
    for s in objective.scores:
        if s.scorer_kind == kind and s.judge_alias == judge:
            return s.value_bool if s.status == "complete" else None
    return None


def _pair_agreement(objectives: list[Objective], kind: str, judge_a: str, judge_b: str) -> PairAgreement:
    agree = 0
    pairs = 0
    a_true = b_true = 0
    for obj in objectives:
        va, vb = _verdict(obj, kind, judge_a), _verdict(obj, kind, judge_b)
        if va is None or vb is None:
            continue
        pairs += 1
        a_true += va
        b_true += vb
        if va == vb:
            agree += 1
    # Cohen's kappa
    kappa = None
    if pairs:
        po = agree / pairs
        pe = ((a_true / pairs) * (b_true / pairs)) + (((pairs - a_true) / pairs) * ((pairs - b_true) / pairs))
        kappa = None if pe >= 1.0 else round((po - pe) / (1 - pe), 4)
    return PairAgreement(
        kind=kind,
        judge_a=judge_a,
        judge_b=judge_b,
        pairs=pairs,
        agreement_pct=_pct(agree, pairs),
        kappa=kappa,
    )


def _self_divergence(objectives: list[Objective], self_judge: str, primary: str) -> SelfDivergence:
    # attack success: lenience/strictness are CONDITIONAL on the primary's verdict
    # (self-lenience = P(self=true | primary=false), self-strictness the mirror).
    lenient = strict = asr_pairs = primary_true = primary_false = 0
    for obj in objectives:
        vs, vp = _verdict(obj, ATTACK_SUCCESS, self_judge), _verdict(obj, ATTACK_SUCCESS, primary)
        if vs is None or vp is None:
            continue
        asr_pairs += 1
        primary_true += vp
        primary_false += not vp
        if vp is False and vs is True:
            lenient += 1  # self claims success where primary says failure
        if vp is True and vs is False:
            strict += 1
    # refusal: self missed refusals the primary saw, conditional on primary refusal
    blind = ref_pairs = primary_refusals = 0
    for obj in objectives:
        vs, vp = _verdict(obj, REFUSAL, self_judge), _verdict(obj, REFUSAL, primary)
        if vs is None or vp is None:
            continue
        ref_pairs += 1
        primary_refusals += vp
        if vp is True and vs is False:
            blind += 1
    return SelfDivergence(
        self_judge=self_judge,
        primary_judge=primary,
        attack_success=DivergenceAttack(
            lenience_pct=_pct(lenient, primary_false),
            strictness_pct=_pct(strict, primary_true),
            pairs=asr_pairs,
        ),
        refusal=DivergenceRefusal(blindness_pct=_pct(blind, primary_refusals), pairs=ref_pairs),
    )


def compute_stats(run: Run, objectives: list[Objective]) -> RunStats:
    outcomes: dict[str, int] = {}
    for obj in objectives:
        outcomes[obj.outcome or "unknown"] = outcomes.get(obj.outcome or "unknown", 0) + 1

    per_judge = [
        JudgeStats(
            judge_alias=judge,
            attack_success=_kind_stats(
                [s for o in objectives for s in o.scores if s.judge_alias == judge], ATTACK_SUCCESS
            ),
            refusal=_kind_stats([s for o in objectives for s in o.scores if s.judge_alias == judge], REFUSAL),
        )
        for judge in run.judges
    ]

    agreement = [
        _pair_agreement(objectives, kind, a, b)
        for kind in (ATTACK_SUCCESS, REFUSAL)
        for a, b in combinations(run.judges, 2)
    ]

    divergence = None
    self_judges = [j for j in run.judges if j == "judge-self"]
    if self_judges and run.primary_judge not in self_judges:
        divergence = _self_divergence(objectives, self_judges[0], run.primary_judge)

    return RunStats(
        run_id=run.id,
        n_objectives=len(objectives),
        per_judge=per_judge,
        agreement=agreement,
        self_divergence=divergence,
        outcome_counts=outcomes,
    )
