"""Analytics tests: rates, undetermined bucketing, kappa, self-divergence."""

import uuid

from app.models import Objective, Run, ScoreRow
from app.services.analytics import compute_stats


def _run() -> Run:
    return Run(
        id=uuid.uuid4(),
        status="complete",
        target_alias="target-model",
        judges=["judge-self", "judge-bf16", "judge-claude"],
        primary_judge="judge-claude",
        prompts=[],
        concurrency=4,
        labels={},
    )


def _score(objective: Objective, kind: str, judge: str, value: bool | None, status: str = "complete") -> ScoreRow:
    return ScoreRow(
        objective_id=objective.id,
        scorer_kind=kind,
        judge_alias=judge,
        score_type="true_false",
        value_bool=value,
        status=status,
        rationale="",
    )


def _objective(run: Run, seq: int, *, asr: bool, self_asr: bool | None = None) -> Objective:
    """One objective where bf16/claude agree and self may diverge."""
    obj = Objective(run_id=run.id, seq=seq, prompt=f"p{seq}", outcome="failure")
    scores = [
        _score(obj, "attack_success", "judge-claude", asr),
        _score(obj, "refusal", "judge-claude", not asr),
        _score(obj, "attack_success", "judge-bf16", asr),
        _score(obj, "refusal", "judge-bf16", not asr),
    ]
    if self_asr is None:
        scores += [
            _score(obj, "attack_success", "judge-self", None, status="undetermined"),
            _score(obj, "refusal", "judge-self", not asr),
        ]
    else:
        scores += [
            _score(obj, "attack_success", "judge-self", self_asr),
            _score(obj, "refusal", "judge-self", not asr),
        ]
    obj.scores = scores
    return obj


def test_rates_and_undetermined_bucket():
    run = _run()
    objectives = [
        _objective(run, 0, asr=False),                    # self: undetermined
        _objective(run, 1, asr=True, self_asr=True),      # self: complete true
        _objective(run, 2, asr=False, self_asr=False),    # self: complete false
    ]

    stats = compute_stats(run, objectives)
    by_judge = {j.judge_alias: j for j in stats.per_judge}

    claude = by_judge["judge-claude"].attack_success
    assert (claude.true, claude.false, claude.undetermined) == (1, 2, 0)
    assert claude.rate_pct == 33.33

    self_stats = by_judge["judge-self"].attack_success
    assert self_stats.undetermined == 1
    assert self_stats.rate_pct == 50.0  # 1 true of 2 complete


def test_kappa_hand_computed():
    run = _run()
    objectives = [
        _objective(run, 0, asr=False, self_asr=True),
        _objective(run, 1, asr=True, self_asr=True),
        _objective(run, 2, asr=False, self_asr=False),
    ]
    stats = compute_stats(run, objectives)
    pair = next(a for a in stats.agreement if a.kind == "attack_success" and {a.judge_a, a.judge_b} == {"judge-self", "judge-bf16"})
    # self=[T,T,F] vs bf16=[F,T,F]: agree 2/3, pe=4/9, kappa=(2/3-4/9)/(5/9)=0.4
    assert pair.pairs == 3
    assert pair.agreement_pct == 66.67
    assert pair.kappa == 0.4


def test_self_divergence_lenience():
    run = _run()
    objectives = [
        _objective(run, 0, asr=False, self_asr=True),  # lenient: primary F, self T
        _objective(run, 1, asr=True, self_asr=True),
        _objective(run, 2, asr=False, self_asr=False),
    ]
    stats = compute_stats(run, objectives)
    d = stats.self_divergence
    assert d is not None
    assert d.attack_success.lenience_pct == 50.0  # 1 of 2 primary-false pairs
    assert d.attack_success.strictness_pct == 0.0
    assert d.refusal.blindness_pct == 0.0
