"""Derived analysis views over runs: per-prompt joins, filters, comparisons.

Reads run artifacts via :mod:`src.web.runs` and produces the JSON payloads
behind ``/api/runs/{name}/prompts`` and ``/api/compare``.
"""

from src.csv_io import load_csv
from src.metrics import effective_score
from src.run_meta import read_meta
from src.scorers import REFUSAL_ASR_COUNTERPART
from src.web.runs import SUMMARY_FILES, run_path, scorers_in_run

QUADRANTS = ("breach", "scarecrow", "guarded", "fizzle")


def _quadrant(asr_val: str, ref_val: str) -> str | None:
    if asr_val == "true" and ref_val == "false":
        return "breach"
    if asr_val == "true" and ref_val == "true":
        return "scarecrow"
    if asr_val == "false" and ref_val == "true":
        return "guarded"
    if asr_val == "false" and ref_val == "false":
        return "fizzle"
    return None


def load_prompt_rows(run_name: str) -> tuple[list[dict], list[str]]:
    """Join raw responses with every scored file by conversation_id.

    Returns ``(rows, scorers)``.  Each row carries ``scores`` (per scorer
    value/rationale) and ``quadrants`` (per refusal scorer with an ASR
    counterpart present).
    """
    d = run_path(run_name)
    raw = load_csv(d / "raw_responses.csv")
    scorers = scorers_in_run(d)

    score_index: dict[str, dict[str, dict]] = {}
    for s in scorers:
        score_index[s] = {
            r["conversation_id"]: {
                "value": r.get("score_value", ""),
                "rationale": r.get("score_rationale", ""),
            }
            for r in load_csv(d / f"scored_{s}.csv")
        }

    rows = []
    for r in raw:
        cid = r["conversation_id"]
        scores = {s: score_index[s].get(cid) for s in scorers}
        quadrants: dict[str, str | None] = {}
        for ref_scorer, asr_scorer in REFUSAL_ASR_COUNTERPART.items():
            if ref_scorer in score_index and asr_scorer in score_index:
                asr = score_index[asr_scorer].get(cid)
                ref = score_index[ref_scorer].get(cid)
                if asr and ref:
                    quadrants[ref_scorer] = _quadrant(
                        effective_score(asr["value"], refusal=False),
                        effective_score(ref["value"], refusal=True),
                    )
        rows.append({
            "objective": r.get("objective", ""),
            "last_response": r.get("last_response", ""),
            "strategy": r.get("strategy", ""),
            "conversation_id": cid,
            "executed_turns": r.get("executed_turns", ""),
            "execution_time_ms": r.get("execution_time_ms", ""),
            "pyrit_outcome": r.get("pyrit_outcome", ""),
            "pyrit_outcome_reason": r.get("pyrit_outcome_reason", ""),
            "scores": scores,
            "quadrants": quadrants,
        })
    return rows, scorers


def _asr_effective_values(row: dict) -> list[str]:
    vals = []
    for s, sc in row["scores"].items():
        if s.startswith("asr_") and sc:
            vals.append(effective_score(sc["value"], refusal=False))
    return [v for v in vals if v in ("true", "false")]


def filter_prompt_rows(
    rows: list[dict],
    flt: str | None = None,
    q: str | None = None,
    scorer: str | None = None,
    value: str | None = None,
    quadrant: str | None = None,
) -> list[dict]:
    ql = (q or "").lower()

    def match(r: dict) -> bool:
        if ql and ql not in r["objective"].lower() and ql not in r["last_response"].lower():
            return False
        if scorer and value:
            sc = r["scores"].get(scorer)
            if not sc or sc["value"] != value:
                return False
        if quadrant:
            qvals = [v for v in r["quadrants"].values() if v]
            if quadrant not in qvals:
                return False
        values = [sc["value"] for sc in r["scores"].values() if sc]
        if flt == "errors" and "error" not in values:
            return False
        if flt == "undetermined" and "undetermined" not in values:
            return False
        if flt == "cpv" and "content_policy_violation" not in values:
            return False
        if flt == "disagreement":
            asr_vals = _asr_effective_values(r)
            if len(asr_vals) < 2 or len(set(asr_vals)) != 2:
                ref_vals = [
                    effective_score(sc["value"], refusal=True)
                    for s, sc in r["scores"].items()
                    if s.startswith(("strict_", "lenient_")) and sc
                ]
                ref_vals = [v for v in ref_vals if v in ("true", "false")]
                if len(ref_vals) < 2 or len(set(ref_vals)) != 2:
                    return False
        return True

    return [r for r in rows if match(r)]


# ── Cross-run comparison ───────────────────────────────────────────

def compare_summaries(run_names: list[str], kind: str) -> dict:
    """Merge one summary kind across runs: metric rows x run columns."""
    columns = []
    metric_values: dict[str, dict[str, str]] = {}
    metric_order: list[str] = []
    for name in run_names:
        rows = load_csv(run_path(name) / SUMMARY_FILES[kind])
        meta = read_meta(run_path(name))
        tier = meta.get("tier") or "?"
        columns.append({"run": name, "tier": tier})
        for row in rows:
            metric = row.get("metric", "")
            if metric not in metric_values:
                metric_values[metric] = {}
                metric_order.append(metric)
            for k, v in row.items():
                if k != "metric":
                    metric_values[metric][f"{name}::{k}"] = v
    return {
        "kind": kind,
        "columns": columns,
        "metrics": [
            {"metric": m, "values": metric_values[m]} for m in metric_order
        ],
    }


def compare_prompts(run_names: list[str]) -> dict:
    """Join runs on objective text: per-objective verdicts across runs."""
    by_objective: dict[str, dict] = {}
    order: list[str] = []
    for name in run_names:
        rows, _ = load_prompt_rows(name)
        for r in rows:
            obj = r["objective"]
            if obj not in by_objective:
                by_objective[obj] = {"objective": obj, "runs": {}}
                order.append(obj)
            entry = {
                "pyrit_outcome": r["pyrit_outcome"],
                "scores": {s: sc["value"] for s, sc in r["scores"].items() if sc},
            }
            by_objective[obj]["runs"][name] = entry

    tiers = {name: read_meta(run_path(name)).get("tier") or "?" for name in run_names}
    return {
        "runs": run_names,
        "tiers": tiers,
        "objectives": [by_objective[o] for o in order],
    }
