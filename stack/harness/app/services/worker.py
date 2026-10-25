"""Run worker: PyRIT attack execution -> Postgres rows.

Orchestration only — PyRIT construction lives in ``app.pyrit``, extraction in
``app.pyrit.extract``, DB access via ``app.db``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pyrit.executor.attack import AttackExecutor, AttackScoringConfig, PromptSendingAttack
from pyrit.memory import CentralMemory
from sqlalchemy import select

from app import litellm
from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Objective, Run, ScoreRow, Turn
from app.pyrit import extract
from app.pyrit.judges import build_judge_matrix
from app.pyrit.lifecycle import ensure_pyrit
from app.pyrit.targets import build_target

logger = logging.getLogger("harness.worker")

TERMINAL_STATUSES = {"complete", "error"}


async def _set_run(run_id: uuid.UUID, **fields) -> None:
    async with AsyncSessionLocal() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        await session.commit()


async def _persist_result(run_id: uuid.UUID, seq: int, objective_text: str, result) -> None:
    # pyrit 1.1.0 ships only the sync getters (async variants land in 1.2);
    # against IN_MEMORY SQLite these are in-process and fast.
    memory = CentralMemory.get_memory_instance()
    pieces = memory.get_message_pieces(conversation_id=result.conversation_id)
    scores = memory.get_prompt_scores(conversation_id=result.conversation_id)

    async with AsyncSessionLocal() as session:
        objective = Objective(
            run_id=run_id,
            seq=seq,
            prompt=objective_text,
            conversation_id=result.conversation_id,
            outcome=extract.outcome_str(result.outcome),
            outcome_reason=result.outcome_reason,
            executed_turns=result.executed_turns,
            execution_time_ms=result.execution_time_ms,
        )
        objective.turns = [Turn(objective_id=objective.id, **t) for t in extract.turns_from_pieces(list(pieces))]
        objective.scores = [ScoreRow(objective_id=objective.id, **row) for row in extract.score_rows_from_memory(list(scores))]
        session.add(objective)
        await session.commit()


async def _persist_failure(run_id: uuid.UUID, seq: int, objective_text: str, exc: BaseException) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Objective(
                run_id=run_id,
                seq=seq,
                prompt=objective_text,
                outcome="error",
                outcome_reason=repr(exc)[:2000],
            )
        )
        await session.commit()


async def execute_run(run_id: uuid.UUID) -> None:
    """Run all objectives of a run; persist one discrete result per objective."""
    await ensure_pyrit()

    async with AsyncSessionLocal() as session:
        run = await session.get(Run, run_id)
        if run is None:
            logger.error("run %s vanished before execution", run_id)
            return
        prompts: list[str] = list(run.prompts)
        target_alias = run.target_alias
        judge_list = list(run.judges)
        primary = run.primary_judge
        concurrency = min(run.concurrency, settings.max_run_concurrency)
        labels = dict(run.labels)

    await _set_run(run_id, status="running")

    try:
        matrix = build_judge_matrix(judge_list, primary)
        await _set_run(run_id, routing_snapshot=await litellm.routing_snapshot([target_alias, *judge_list]))

        attack = PromptSendingAttack(
            objective_target=build_target(target_alias),
            attack_scoring_config=AttackScoringConfig(
                objective_scorer=matrix.objective_scorer,
                auxiliary_scorers=matrix.auxiliary_scorers,
            ),
        )

        executor_result = await AttackExecutor(max_concurrency=concurrency).execute_attack_async(
            attack=attack,
            objectives=prompts,
            return_partial_on_failure=True,
            memory_labels={"run_id": str(run_id), "stack": "v2", **labels},
        )

        # completed_results[i] was produced by objectives[input_indices[i]]
        seq_of = {text: i for i, text in enumerate(prompts)}
        for result, input_index in zip(executor_result.completed_results, executor_result.input_indices):
            try:
                await _persist_result(run_id, input_index, prompts[input_index], result)
            except Exception:  # noqa: BLE001 — one bad objective must not sink the run
                logger.exception("persist failed for objective %s", input_index)

        used_seqs = set(executor_result.input_indices)
        for objective_text, exc in executor_result.incomplete_objectives:
            seq = seq_of.get(objective_text)
            if seq is None or seq in used_seqs:
                # duplicate objective texts: fall back to first unused slot
                seq = next(
                    (i for i, text in enumerate(prompts) if text == objective_text and i not in used_seqs), None
                )
            if seq is None:
                continue
            used_seqs.add(seq)
            await _persist_failure(run_id, seq, objective_text, exc)

        await _set_run(run_id, status="complete", completed_at=datetime.now(UTC))
    except Exception as exc:  # noqa: BLE001
        logger.exception("run %s failed", run_id)
        await _set_run(run_id, status="error", error=repr(exc)[:4000], completed_at=datetime.now(UTC))


async def run_objectives(run_id: uuid.UUID) -> list[Objective]:
    """All objectives of a run, eagerly loaded with turns and scores."""
    from sqlalchemy.orm import selectinload

    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(Objective)
                    .where(Objective.run_id == run_id)
                    .options(selectinload(Objective.turns), selectinload(Objective.scores))
                    .order_by(Objective.seq)
                )
            )
            .scalars()
            .unique()
            .all()
        )
