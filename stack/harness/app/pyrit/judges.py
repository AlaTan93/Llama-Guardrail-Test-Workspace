"""Judge construction: the 3 judges x 2 rubrics scorer matrix.

Judge identity is stamped into every score via ``score_category`` using the
convention ``"<kind>::<judge_alias>"`` so scores read back from PyRIT memory
can be attributed without guessing from scorer class names.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyrit.models import SeedPrompt
from pyrit.score import (
    RefusalScorerPaths,
    SelfAskRefusalScorer,
    SelfAskTrueFalseScorer,
    TrueFalseQuestion,
    TrueFalseQuestionPaths,
)

from app.config import settings
from app.pyrit.targets import build_target

ATTACK_SUCCESS_KIND = "attack_success"
REFUSAL_KIND = "refusal"

# The STRICT refusal rubric counts deflection/hedging/partial answers as
# refusal, matching the legacy pipeline's OBJECTIVE_STRICT choice.
_REFUSAL_SYSTEM_PROMPT = SeedPrompt.from_yaml_file(RefusalScorerPaths.OBJECTIVE_STRICT.value)


def category(kind: str, judge_alias: str) -> str:
    return f"{kind}::{judge_alias}"


def parse_category(value: list[str] | str | None) -> tuple[str, str] | None:
    """Extract (kind, judge_alias) from a score_category like 'refusal::judge-claude'."""
    if not value:
        return None
    first = value[0] if isinstance(value, list) else str(value)
    if "::" not in first:
        return None
    kind, alias = first.split("::", 1)
    return kind, alias


def build_attack_success_scorer(judge_alias: str) -> SelfAskTrueFalseScorer:
    """Attack-success scorer with the shared TASK_ACHIEVED rubric.

    The question is loaded from PyRIT's built-in rubric so every judge gets a
    byte-identical prompt; only ``category`` (judge identity) differs.
    """
    question = TrueFalseQuestion.from_yaml(TrueFalseQuestionPaths.TASK_ACHIEVED.value).model_copy(
        update={"category": category(ATTACK_SUCCESS_KIND, judge_alias)}
    )
    return SelfAskTrueFalseScorer.from_question(
        chat_target=build_target(judge_alias, temperature=settings.judge_temperature),
        question=question,
    )


def build_refusal_scorer(judge_alias: str) -> SelfAskRefusalScorer:
    """Strict refusal scorer (true = the target refused)."""
    return SelfAskRefusalScorer(
        chat_target=build_target(judge_alias, temperature=settings.judge_temperature),
        system_prompt=_REFUSAL_SYSTEM_PROMPT,
        score_category=category(REFUSAL_KIND, judge_alias),
    )


@dataclass
class JudgeMatrix:
    """The full N judges x 2 kinds scorer set plus PyRIT wiring."""

    objective_scorer: SelfAskTrueFalseScorer
    auxiliary_scorers: list
    judges: list[str]
    primary_judge: str


def build_judge_matrix(judges: list[str], primary_judge: str) -> JudgeMatrix:
    """Build the scorer matrix.

    The primary judge's attack-success scorer is the objective scorer (it
    decides PyRIT's SUCCESS/FAILURE outcome); everything else is auxiliary and
    recorded per response. PromptSendingAttack ignores the dedicated
    refusal_scorer slot (it warns if set), so all refusal scorers go in
    auxiliary_scorers.
    """
    if primary_judge not in judges:
        raise ValueError(f"primary judge {primary_judge!r} not in judge list {judges!r}")

    attack_scorers = {alias: build_attack_success_scorer(alias) for alias in judges}
    refusal_scorers = [build_refusal_scorer(alias) for alias in judges]

    auxiliary: list = refusal_scorers
    auxiliary += [scorer for alias, scorer in attack_scorers.items() if alias != primary_judge]

    return JudgeMatrix(
        objective_scorer=attack_scorers[primary_judge],
        auxiliary_scorers=auxiliary,
        judges=list(judges),
        primary_judge=primary_judge,
    )
