from src.config import RAW_FIELDS, SCORED_FIELDS
from src.csv_io import count_rows, load_csv, write_csv
from src.progress import ProgressReporter
from src.scoring import invalidate_scores, score_pyrit_outcomes


def _make_run(tmp_path):
    d = tmp_path / "run_20990101000000000"
    d.mkdir()
    write_csv(d / "raw_responses.csv", [
        {"objective": "a", "last_response": "ra", "strategy": "baseline",
         "conversation_id": "c1", "executed_turns": "1", "execution_time_ms": "1",
         "pyrit_outcome": "success", "pyrit_outcome_reason": "y"},
        {"objective": "b", "last_response": "rb", "strategy": "baseline",
         "conversation_id": "c2", "executed_turns": "1", "execution_time_ms": "1",
         "pyrit_outcome": "failure", "pyrit_outcome_reason": "n"},
    ], RAW_FIELDS)
    write_csv(d / "scored_asr_claude.csv", [
        {"objective": "a", "last_response": "ra", "strategy": "baseline",
         "conversation_id": "c1", "score_value": "true", "score_rationale": "",
         "scorer_type": "asr_claude", "executed_turns": "1", "execution_time_ms": "1"},
    ], SCORED_FIELDS)
    return d


class TickCollector(ProgressReporter):
    def __init__(self):
        self.ticks = []

    def scorer_tick(self, scorer_type, done, total):
        self.ticks.append((scorer_type, done, total))


def test_score_pyrit_outcomes_subset_and_progress(tmp_path):
    d = _make_run(tmp_path)
    collector = TickCollector()
    score_pyrit_outcomes(
        load_csv(d / "raw_responses.csv"), str(d),
        conversation_ids={"c1"}, progress=collector,
    )
    rows = load_csv(d / "scored_asr_pyrit.csv")
    assert [r["conversation_id"] for r in rows] == ["c1"]
    assert rows[0]["score_value"] == "true"  # from pyrit_outcome success
    assert collector.ticks == [("asr_pyrit", 1, 1)]


def test_score_pyrit_outcomes_full_run(tmp_path):
    d = _make_run(tmp_path)
    score_pyrit_outcomes(load_csv(d / "raw_responses.csv"), str(d))
    rows = load_csv(d / "scored_asr_pyrit.csv")
    assert {r["conversation_id"]: r["score_value"] for r in rows} == {"c1": "true", "c2": "false"}


def test_invalidate_scores_drops_ids(tmp_path):
    d = _make_run(tmp_path)
    dropped = invalidate_scores(str(d), {"c1"})
    assert dropped == {"asr_claude": 1}
    assert count_rows(d / "scored_asr_claude.csv") == 0


def test_invalidate_scores_discovers_all_scorers(tmp_path):
    d = _make_run(tmp_path)
    dropped = invalidate_scores(str(d), {"c9"})
    assert dropped == {}


def test_rescore_subset_end_to_end(tmp_path):
    """Invalidation + re-extraction leaves a consistent file."""
    d = _make_run(tmp_path)
    invalidate_scores(str(d), {"c1"})
    score_pyrit_outcomes(load_csv(d / "raw_responses.csv"), str(d), conversation_ids={"c1"})
    rows = load_csv(d / "scored_asr_pyrit.csv")
    assert len(rows) == 1
