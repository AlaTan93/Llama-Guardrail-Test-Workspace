"""Extraction tests: memory scores -> deduped rows, pieces -> turns.

Constructs real pyrit Score/MessagePiece models so the tests exercise the
same wire objects the engine sees.
"""

from datetime import UTC, datetime, timedelta

from pyrit.models import MessagePiece, Score

from app.pyrit.extract import outcome_str, score_rows_from_memory, turns_from_pieces


def _score(category_label: str, *, value="true", status="complete", minutes=0, rationale="r") -> Score:
    return Score(
        score_value=None if status == "undetermined" else value,
        status=status,
        score_type="true_false",
        score_category=[category_label],
        score_rationale=rationale,
        timestamp=datetime.now(UTC) + timedelta(minutes=minutes),
    )


def test_rows_attributed_by_kind_and_judge():
    rows = score_rows_from_memory(
        [
            _score("attack_success::judge-claude", value="false"),
            _score("refusal::judge-claude", value="true"),
        ]
    )
    cells = {(r["scorer_kind"], r["judge_alias"]): r for r in rows}
    assert cells[("attack_success", "judge-claude")]["value_bool"] is False
    assert cells[("refusal", "judge-claude")]["value_bool"] is True


def test_undetermined_has_no_value_and_is_flagged():
    rows = score_rows_from_memory([_score("attack_success::judge-self", status="undetermined")])
    assert rows[0]["value_bool"] is None
    assert rows[0]["status"] == "undetermined"


def test_latest_score_wins_per_cell():
    rows = score_rows_from_memory(
        [
            _score("attack_success::judge-self", value="false", minutes=0, rationale="retry 1"),
            _score("attack_success::judge-self", value="true", minutes=1, rationale="retry 2"),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["value_bool"] is True
    assert rows[0]["rationale"] == "retry 2"


def test_scores_without_category_are_skipped():
    rows = score_rows_from_memory([_score("no-marker")])
    assert rows == []


def test_turns_from_pieces_preserve_order_and_role():
    pieces = [
        MessagePiece(role="user", original_value="hello"),
        MessagePiece(role="assistant", original_value="I'm sorry."),
    ]
    turns = turns_from_pieces(pieces)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[1]["content"] == "I'm sorry."


def test_outcome_str_normalizes_enums_and_strings():
    assert outcome_str("failure") == "failure"

    class FakeOutcome:
        value = "success"

    assert outcome_str(FakeOutcome()) == "success"
