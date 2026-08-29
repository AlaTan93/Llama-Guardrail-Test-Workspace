"""Summary CSV generation.

Produces ``summary.csv`` (ASR), ``summary_refusal.csv`` (refusal), and
``summary_crosstab.csv`` (joint ASR x guardrail distribution) from scored files.
"""

import csv
from pathlib import Path

from src.metrics import (
    compute_agreement,
    compute_f1,
    count_asr,
    count_crosstab,
    count_refusal,
)
from src.scorers import REFUSAL_ASR_COUNTERPART


def _write_rows(path: Path, rows: list[dict], models: list[str], label: str) -> None:
    fields = ["metric"] + models
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{label} written to {path}")


def _build_count_and_rate_rows(
    all_counts: dict[str, dict[str, int]],
    models: list[str],
    count_labels: list[str],
    rate_specs: list[tuple[str, str, str]],
) -> list[dict]:
    """Count rows (one per label) followed by percentage rows.

    *rate_specs* is a list of ``(metric_name, numerator_key, denominator_key)``
    tuples; the rate is ``numerator / denominator * 100``.
    """
    rows: list[dict] = []
    for label in count_labels:
        row: dict[str, str | int | float] = {"metric": label}
        for s in models:
            row[s] = all_counts[s].get(label, 0)
        rows.append(row)

    for metric_name, num_key, den_key in rate_specs:
        row = {"metric": metric_name}
        for s in models:
            c = all_counts[s]
            row[s] = round(c[num_key] / c[den_key] * 100, 2) if c[den_key] else 0.0
        rows.append(row)
    return rows


def _build_diagnostic_rows(
    run_dir: str,
    models: list[str],
    reference: str,
    refusal: bool,
) -> list[dict]:
    """Agreement + precision / recall / F1 rows vs a reference judge.

    The reference judge gets 100.0 for all metrics; every other model is
    compared against the reference's scored file.
    """
    ref_path = Path(run_dir) / f"scored_{reference}.csv"

    agreement_row: dict[str, str | int | float] = {"metric": f"agreement_with_{reference}_pct"}
    f1_data: dict[str, dict[str, float]] = {}
    for s in models:
        if s == reference:
            agreement_row[s] = 100.0
            f1_data[s] = {"precision": 100.0, "recall": 100.0, "f1": 100.0}
        else:
            s_path = Path(run_dir) / f"scored_{s}.csv"
            agreement_row[s] = compute_agreement(s_path, ref_path, refusal=refusal)
            f1_data[s] = compute_f1(s_path, ref_path, refusal=refusal)

    rows = [agreement_row]
    for metric_name, key in [
        (f"precision_vs_{reference}_pct", "precision"),
        (f"recall_vs_{reference}_pct", "recall"),
        (f"f1_vs_{reference}_pct", "f1"),
    ]:
        row: dict[str, str | int | float] = {"metric": metric_name}
        for s in models:
            row[s] = f1_data[s][key]
        rows.append(row)
    return rows


# ── ASR summary ────────────────────────────────────────────────────

def write_summary_asr(run_dir: str, models: list[str], responses: list[dict]) -> None:
    all_counts = {m: count_asr(Path(run_dir) / f"scored_{m}.csv") for m in models}

    rows = _build_count_and_rate_rows(
        all_counts, models,
        count_labels=["total", "success", "failure", "error", "undetermined", "content_policy_violation"],
        rate_specs=[
            ("success_rate_pct", "success", "total"),
            ("cpv_rate_pct", "content_policy_violation", "success"),
        ],
    )
    rows += _build_diagnostic_rows(run_dir, models, "asr_claude", refusal=False)

    _write_rows(Path(run_dir) / "summary.csv", rows, models, "Summary")


# ── Refusal summary ────────────────────────────────────────────────

def _build_capability_gap_row(
    run_dir: str,
    all_counts: dict[str, dict[str, int]],
    models: list[str],
) -> dict:
    """capability_gap = compliance_rate - asr_success_rate.

    Positive and growing at low bits = guardrail broke but capability loss
    masked the harm.  Blank when the ASR counterpart scored file is absent.
    """
    gap_row: dict[str, str | int | float | None] = {"metric": "capability_gap_pct"}
    for s in models:
        asr_key = REFUSAL_ASR_COUNTERPART.get(s)
        gap_row[s] = ""
        if asr_key:
            asr_counts = count_asr(Path(run_dir) / f"scored_{asr_key}.csv")
            c = all_counts[s]
            if c["total"] and asr_counts["total"]:
                asr_rate = asr_counts["success"] / asr_counts["total"] * 100
                comp_rate = c["compliance"] / c["total"] * 100
                gap_row[s] = round(comp_rate - asr_rate, 2)
    return gap_row


def write_summary_refusal(run_dir: str, models: list[str], responses: list[dict]) -> None:
    if not models:
        return

    all_counts = {m: count_refusal(Path(run_dir) / f"scored_{m}.csv") for m in models}

    rows = _build_count_and_rate_rows(
        all_counts, models,
        count_labels=["total", "compliance", "refusal", "error", "undetermined", "content_policy_violation"],
        rate_specs=[
            ("compliance_rate_pct", "compliance", "total"),
            ("refusal_rate_pct", "refusal", "total"),
        ],
    )
    rows += _build_diagnostic_rows(run_dir, models, "strict_claude", refusal=True)
    rows.append(_build_capability_gap_row(run_dir, all_counts, models))

    _write_rows(Path(run_dir) / "summary_refusal.csv", rows, models, "Refusal summary")


# ── Crosstab summary ───────────────────────────────────────────────

def write_summary_crosstab(run_dir: str, refusal_models: list[str]) -> None:
    triples: list[tuple[str, Path, Path]] = []
    for m in refusal_models:
        asr_key = REFUSAL_ASR_COUNTERPART.get(m)
        if not asr_key:
            continue
        asr_path = Path(run_dir) / f"scored_{asr_key}.csv"
        ref_path = Path(run_dir) / f"scored_{m}.csv"
        if asr_path.exists() and ref_path.exists():
            triples.append((m, asr_path, ref_path))

    if not triples:
        return

    judges = [t[0] for t in triples]
    all_counts = {judge: count_crosstab(asr_path, ref_path) for judge, asr_path, ref_path in triples}

    rows: list[dict] = []
    for label in ["total", "breach", "scarecrow", "guarded", "fizzle", "unscorable"]:
        row: dict[str, str | int | float] = {"metric": label}
        for j in judges:
            row[j] = all_counts[j].get(label, 0)
        rows.append(row)

    for label in ["breach", "scarecrow", "guarded", "fizzle"]:
        row = {"metric": f"{label}_pct"}
        for j in judges:
            c = all_counts[j]
            row[j] = round(c[label] / c["total"] * 100, 2) if c["total"] else 0.0
        rows.append(row)

    _write_rows(Path(run_dir) / "summary_crosstab.csv", rows, judges, "Crosstab summary")


# ── Public entry point ─────────────────────────────────────────────

def write_summaries(run_dir: str, models: list[str], responses: list[dict]) -> None:
    """Partition scorers by rubric and emit per-rubric summary files."""
    from src.scorers import is_refusal_scorer

    asr_models = [m for m in models if not is_refusal_scorer(m)]
    refusal_models = [m for m in models if is_refusal_scorer(m)]
    if asr_models:
        write_summary_asr(run_dir, asr_models, responses)
    if refusal_models:
        write_summary_refusal(run_dir, refusal_models, responses)
    write_summary_crosstab(run_dir, refusal_models)
