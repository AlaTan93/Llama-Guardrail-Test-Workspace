"""Pydantic request/response models for the harness API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    prompts: list[str] = Field(min_length=1)
    target_alias: str | None = None  # default: settings.target_alias
    judges: list[str] | None = None  # default: settings.judge_aliases
    primary_judge: str | None = None  # default: settings.primary_judge
    concurrency: int = Field(default=4, ge=1, le=32)
    labels: dict[str, str] = Field(default_factory=dict)
    guardrail_config: dict | None = None  # free-form, stored for A/B comparisons


class TurnOut(BaseModel):
    seq: int
    role: str
    content: str

    model_config = {"from_attributes": True}


class ScoreOut(BaseModel):
    scorer_kind: str
    judge_alias: str
    score_type: str
    value_bool: bool | None
    value_float: float | None
    status: str
    rationale: str | None

    model_config = {"from_attributes": True}


class ObjectiveOut(BaseModel):
    id: uuid.UUID
    seq: int
    prompt: str
    conversation_id: str | None
    outcome: str | None
    outcome_reason: str | None
    executed_turns: int | None
    execution_time_ms: int | None
    turns: list[TurnOut] = []
    scores: list[ScoreOut] = []

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    status: str
    target_alias: str
    judges: list[str]
    primary_judge: str
    concurrency: int
    labels: dict[str, str]
    guardrail_config: dict | None
    routing_snapshot: dict | None
    error: str | None
    completed_at: datetime | None
    n_objectives: int = 0
    n_objectives_done: int = 0

    model_config = {"from_attributes": True}


class KindStats(BaseModel):
    total: int
    true: int
    false: int
    undetermined: int
    rate_pct: float | None  # true-rate over complete verdicts (ASR or refusal rate)


class JudgeStats(BaseModel):
    judge_alias: str
    attack_success: KindStats
    refusal: KindStats


class PairAgreement(BaseModel):
    kind: str
    judge_a: str
    judge_b: str
    pairs: int
    agreement_pct: float | None
    kappa: float | None


class DivergenceAttack(BaseModel):
    lenience_pct: float | None  # P(self=true | primary=false)
    strictness_pct: float | None  # P(self=false | primary=true)
    pairs: int


class DivergenceRefusal(BaseModel):
    blindness_pct: float | None  # P(self=not-refused | primary=refused)
    pairs: int


class SelfDivergence(BaseModel):
    self_judge: str
    primary_judge: str
    attack_success: DivergenceAttack
    refusal: DivergenceRefusal


class RunStats(BaseModel):
    run_id: uuid.UUID
    n_objectives: int
    per_judge: list[JudgeStats]
    agreement: list[PairAgreement]
    self_divergence: SelfDivergence | None
    outcome_counts: dict[str, int]
