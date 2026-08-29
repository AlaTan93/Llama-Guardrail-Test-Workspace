from src.config import RAW_FIELDS
from src.csv_io import (
    backup_file,
    count_rows,
    drop_raw_rows,
    drop_scored_rows,
    load_csv,
    write_csv,
)


def _make(path, rows, fields):
    write_csv(path, rows, fields)
    return path


def test_count_rows(tmp_path):
    p = tmp_path / "x.csv"
    assert count_rows(p) == 0
    _make(p, [{"a": 1}, {"a": 2}], ["a"])
    assert count_rows(p) == 2


def test_drop_scored_rows(tmp_path):
    p = _make(
        tmp_path / "scored_x.csv",
        [
            {"conversation_id": "c1", "score_value": "true"},
            {"conversation_id": "c2", "score_value": "false"},
            {"conversation_id": "c3", "score_value": "true"},
        ],
        ["conversation_id", "score_value"],
    )
    dropped = drop_scored_rows(p, {"c2", "c9"})
    assert dropped == 1
    remaining = [r["conversation_id"] for r in load_csv(p)]
    assert remaining == ["c1", "c3"]


def test_drop_scored_rows_noop_when_absent(tmp_path):
    assert drop_scored_rows(tmp_path / "missing.csv", {"c1"}) == 0


def test_drop_raw_rows_returns_dropped_ids(tmp_path):
    p = _make(
        tmp_path / "raw_responses.csv",
        [
            {"objective": "a", "conversation_id": "c1"},
            {"objective": "b", "conversation_id": "c2"},
            {"objective": "a", "conversation_id": "c3"},
        ],
        RAW_FIELDS[:4],
    )
    dropped, ids = drop_raw_rows(p, {"a"})
    assert dropped == 2
    assert ids == {"c1", "c3"}
    assert [r["objective"] for r in load_csv(p)] == ["b"]


def test_backup_file(tmp_path):
    import re

    p = _make(tmp_path / "raw_responses.csv", [{"objective": "a"}], ["objective"])
    dest = backup_file(p)
    assert dest is not None and dest.exists()
    assert dest.parent.name == "backups"
    assert re.match(r"raw_responses_\d+\.csv", dest.name)
    assert load_csv(dest) == load_csv(p)
    assert backup_file(tmp_path / "missing.csv") is None
