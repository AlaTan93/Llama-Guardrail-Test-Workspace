import argparse
import csv
import sys
from pathlib import Path

NA = "—"

# Display order for the judge rows (reference judge first). Any judge not listed
# here appears after, in order of first appearance in the CSVs.
JUDGE_PRIORITY = ["claude", "bf16", "pyrit"]

# ASR metric names are ambiguous next to refusal ones, so relabel for the box view.
ASR_RELABEL = {"success": "attack_success", "failure": "attack_failure"}


def _load_rows(path: Path) -> list[dict[str, str]] | None:
    """Raw ordered CSV rows. None if file absent or empty."""
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows or None


def _dict_from_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Rows -> {metric: {scorer: value}}."""
    data: dict[str, dict[str, str]] = {}
    for row in rows:
        metric = row["metric"].strip()
        data[metric] = {k.strip(): (v or "").strip() for k, v in row.items() if k != "metric"}
    return data


def _scorers(data: dict[str, dict[str, str]] | None) -> list[str]:
    """Scorer column names in file order."""
    if not data:
        return []
    row = data.get("total") or next(iter(data.values()))
    return list(row.keys())


def _fmt_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a markdown table. Column 0 left-aligned, the rest right-aligned."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def cell(i: int, val: str) -> str:
        s = str(val)
        return s.rjust(widths[i]) if i > 0 else s.ljust(widths[i])

    lines = []
    lines.append("| " + " | ".join(cell(i, h) for i, h in enumerate(headers)) + " |")
    sep = []
    for i in range(len(headers)):
        sep.append("-" * (widths[i] - 1) + ":" if i > 0 else "-" * widths[i])
    lines.append("| " + " | ".join(sep) + " |")
    for row in rows:
        lines.append("| " + " | ".join(cell(i, c) for i, c in enumerate(row)) + " |")
    return "\n".join(lines)


def _fmt_box(rows: list[dict[str, str]], relabel: dict[str, str] | None = None) -> str:
    """Plain-text box table: '=' top border, right-justified columns, '-+-' sep.
    Matches the main.py summary style. If relabel is given it is applied to the
    first (metric) column values before widths are computed."""
    headers = list(rows[0].keys())
    disp: list[dict[str, str]] = []
    for r in rows:
        dr = dict(r)
        if relabel:
            dr[headers[0]] = relabel.get(dr[headers[0]], dr[headers[0]])
        disp.append(dr)
    widths = {h: max(len(h), max(len(str(r.get(h, ""))) for r in disp)) for h in headers}
    header_line = " | ".join(h.rjust(widths[h]) for h in headers)
    sep_line = "-+-".join("-" * widths[h] for h in headers)
    border = "=" * (sum(widths.values()) + 3 * (len(headers) - 1))
    data_lines = [" | ".join(str(r.get(h, "")).rjust(widths[h]) for h in headers) for r in disp]
    return "\n".join([border, header_line, sep_line] + data_lines)


_RUBRIC_PREFIXES = ("asr_", "strict_", "lenient_")


def _base_judge(scorer: str) -> str:
    """Strip the rubric prefix to get the base judge name."""
    for p in _RUBRIC_PREFIXES:
        if scorer.startswith(p):
            return scorer[len(p):]
    return scorer


def _base_judges(asr_scorers: list[str], ref_scorers: list[str]) -> list[str]:
    """Union of ASR scorers and refusal scorers (reduced to base judge names), ordered."""
    base: list[str] = []
    for s in asr_scorers + ref_scorers:
        judge = _base_judge(s)
        if judge not in base:
            base.append(judge)
    base.sort(key=lambda j: JUDGE_PRIORITY.index(j) if j in JUDGE_PRIORITY else len(JUDGE_PRIORITY))
    return base


def build_tables(run_dir: Path) -> str:
    asr_rows = _load_rows(run_dir / "summary.csv")
    if not asr_rows:
        raise FileNotFoundError(f"summary.csv not found in {run_dir}")
    asr = _dict_from_rows(asr_rows)
    ref_rows = _load_rows(run_dir / "summary_refusal.csv")  # optional
    ref = _dict_from_rows(ref_rows) if ref_rows else None
    cross_rows = _load_rows(run_dir / "summary_crosstab.csv")  # optional

    asr_scorers = _scorers(asr)
    ref_scorers = _scorers(ref)
    base = _base_judges(asr_scorers, ref_scorers)

    def asr_val(metric: str, judge: str) -> str:
        key = "asr_" + judge
        if asr and key in asr.get(metric, {}):
            v = asr[metric][key]
            return v if v != "" else NA
        return NA

    def ref_val(metric: str, judge: str) -> str:
        key = "strict_" + judge
        if ref and key in ref.get(metric, {}):
            v = ref[metric][key]
            return v if v != "" else NA
        return NA

    def total_val(judge: str) -> str:
        v = asr_val("total", judge)
        return ref_val("total", judge) if v == NA else v

    headers = ["judge", "total", "ASR success %", "compliance %", "refusal %", "capability gap %"]
    rows = []
    for j in base:
        rows.append([
            j,
            total_val(j),
            asr_val("success_rate_pct", j),
            ref_val("compliance_rate_pct", j),
            ref_val("refusal_rate_pct", j),
            ref_val("capability_gap_pct", j),
        ])

    diag_headers = ["judge", "agreement %", "precision %", "recall %", "f1 %"]
    diag_rows = []
    for j in base:
        # Prefer refusal-side diagnostics when the judge has a strict refusal
        # counterpart (strict_claude is the reference for the refusal rubric).
        if ref is not None and ("strict_" + j) in ref_scorers:
            ag, pr, rc, f1 = (
                ref_val("agreement_with_strict_claude_pct", j),
                ref_val("precision_vs_strict_claude_pct", j),
                ref_val("recall_vs_strict_claude_pct", j),
                ref_val("f1_vs_strict_claude_pct", j),
            )
        else:
            ag, pr, rc, f1 = (
                asr_val("agreement_with_asr_claude_pct", j),
                asr_val("precision_vs_asr_claude_pct", j),
                asr_val("recall_vs_asr_claude_pct", j),
                asr_val("f1_vs_asr_claude_pct", j),
            )
        diag_rows.append([j, ag, pr, rc, f1])
    out = [_fmt_table(headers, rows), "", "Diagnostics (vs reference judge)", _fmt_table(diag_headers, diag_rows)]

    if asr_rows:
        out += ["", "ASR", _fmt_box(asr_rows, relabel=ASR_RELABEL)]
    if ref_rows:
        out += ["", "Refusal", _fmt_box(ref_rows)]
    if cross_rows:
        out += ["", "Crosstab (ASR \u00d7 Guardrail)", _fmt_box(cross_rows)]

    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a run's summary.csv + summary_refusal.csv as a markdown comparison table"
    )
    parser.add_argument("--run-dir", required=True, help="Run directory containing summary.csv")
    parser.add_argument("--out", default=None, help="Write markdown to this file instead of stdout")
    args = parser.parse_args()

    text = build_tables(Path(args.run_dir))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
