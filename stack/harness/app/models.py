"""Postgres system-of-record: runs -> objectives -> turns/scores.

PyRIT memory stays IN_MEMORY per process; these tables are the durable copy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(Text, default="queued")  # queued|running|complete|error
    target_alias: Mapped[str] = mapped_column(Text)
    judges: Mapped[list] = mapped_column(JSONB, default=list)
    primary_judge: Mapped[str] = mapped_column(Text)
    prompts: Mapped[list] = mapped_column(JSONB, default=list)
    concurrency: Mapped[int] = mapped_column(Integer, default=4)
    labels: Mapped[dict] = mapped_column(JSONB, default=dict)
    guardrail_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    routing_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    objectives: Mapped[list["Objective"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Objective.seq"
    )


class Objective(Base):
    __tablename__ = "objectives"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)  # success|failure|error|undetermined
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run: Mapped[Run] = relationship(back_populates="objectives")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="objective", cascade="all, delete-orphan", order_by="Turn.seq"
    )
    scores: Mapped[list["ScoreRow"]] = relationship(
        back_populates="objective", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    objective_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("objectives.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text)  # user|assistant|system|simulated_assistant
    content: Mapped[str] = mapped_column(Text)

    objective: Mapped[Objective] = relationship(back_populates="turns")


class ScoreRow(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("objective_id", "scorer_kind", "judge_alias", name="uq_score_cell"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    objective_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("objectives.id", ondelete="CASCADE"), index=True)
    scorer_kind: Mapped[str] = mapped_column(Text)  # attack_success|refusal
    judge_alias: Mapped[str] = mapped_column(Text)  # judge-self|judge-bf16|judge-claude|...
    score_type: Mapped[str] = mapped_column(Text)  # true_false|float_scale
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_float: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text)  # complete|undetermined
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    objective: Mapped[Objective] = relationship(back_populates="scores")
