"""Extraction: PyRIT memory objects -> plain rows for Postgres.

Reads ``score_value``/``status`` fields directly instead of ``get_value()`` /
``is_undetermined`` — their shape drifted between the 1.1.0 wheel (property)
and GitHub main (method), while the raw fields are stable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pyrit.models import Score

from app.pyrit.judges import parse_category


def _status_of(score: Score) -> str:
    return str(getattr(score.status, "value", score.status))


def score_rows_from_memory(scores: list[Score]) -> list[dict]:
    """Deduplicate memory scores into one row per (kind, judge), latest wins."""
    latest: dict[tuple[str, str], tuple[datetime, dict]] = {}
    for score in scores:
        parsed = parse_category(score.score_category)
        if parsed is None:
            continue
        kind, alias = parsed
        ts = score.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        status = _status_of(score)
        value_bool: bool | None = None
        value_float: float | None = None
        if status == "complete" and score.score_value is not None:
            if str(score.score_type).endswith("true_false"):
                value_bool = str(score.score_value).strip().lower() == "true"
            else:
                try:
                    value_float = float(score.score_value)
                except (TypeError, ValueError):
                    status = "undetermined"

        row = {
            "scorer_kind": kind,
            "judge_alias": alias,
            "score_type": str(score.score_type),
            "value_bool": value_bool,
            "value_float": value_float,
            "status": status,
            "rationale": score.score_rationale,
        }
        if (kind, alias) not in latest or ts >= latest[(kind, alias)][0]:
            latest[(kind, alias)] = (ts, row)
    return [row for _, row in latest.values()]


def turns_from_pieces(pieces: list) -> list[dict]:
    """Conversation transcript rows from memory message pieces."""
    turns = []
    for piece in pieces:
        content = piece.original_value or piece.converted_value or ""
        turns.append(
            {
                "seq": piece.sequence if piece.sequence >= 0 else len(turns),
                "role": str(getattr(piece.role, "value", piece.role)),
                "content": str(content),
            }
        )
    return turns


def outcome_str(outcome) -> str:
    """Normalize an AttackOutcome enum (or str) for storage."""
    return str(getattr(outcome, "value", outcome))
