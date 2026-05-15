import argparse
import csv
import sys
from pathlib import Path

from src.redteam import RAW_FIELDS
from src.scoring import SCORED_FIELDS, _write_summary

RESULTS_DIR = Path(__file__).parent / "results"


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_run_dir(name: str) -> Path:
    p = Path(name)
    if p.is_dir():
        return p.resolve()
    candidate = RESULTS_DIR / name
    if candidate.is_dir():
        return candidate.resolve()
    print(f"Error: run directory not found: {name} (tried {p} and {candidate})")
    sys.exit(1)


def _find_scored_scorers(run_dir: Path) -> set[str]:
    scorers = set()
    for f in run_dir.glob("scored_*.csv"):
        scorer = f.stem.removeprefix("scored_")
        scorers.add(scorer)
    return scorers


def merge_runs(target: Path, sources: list[Path]) -> None:
    all_dirs = [target] + sources

    print("Target:", target.name)
    print("Sources:", ", ".join(s.name for s in sources))
    print()

    for d in all_dirs:
        raw = d / "raw_responses.csv"
        if not raw.exists():
            print(f"Error: {raw} not found")
            sys.exit(1)

    print("--- Merging raw_responses.csv ---")
    all_raw: list[dict] = []
    for d in all_dirs:
        rows = _load_csv(d / "raw_responses.csv")
        print(f"  {d.name}: {len(rows)} rows")
        all_raw.extend(rows)

    _write_csv(target / "raw_responses.csv", all_raw, RAW_FIELDS)
    print(f"  => merged total: {len(all_raw)} rows")
    print()

    print("--- Merging scored files ---")
    scorer_sets = [_find_scored_scorers(d) for d in all_dirs]
    common_scorers = set(scorer_sets[0])
    for s in scorer_sets[1:]:
        common_scorers &= s

    all_scorers = set(scorer_sets[0])
    for s in scorer_sets[1:]:
        all_scorers |= s

    for s in all_scorers - common_scorers:
        missing = [d.name for d, ss in zip(all_dirs, scorer_sets) if s not in ss]
        print(f"  WARNING: scorer '{s}' missing from {', '.join(missing)} — skipped")

    merged_scorers: list[str] = []
    for scorer in sorted(common_scorers):
        all_scored: list[dict] = []
        for d in all_dirs:
            path = d / f"scored_{scorer}.csv"
            rows = _load_csv(path)
            print(f"  scored_{scorer}.csv [{d.name}]: {len(rows)} rows")
            all_scored.extend(rows)

        _write_csv(target / f"scored_{scorer}.csv", all_scored, SCORED_FIELDS)
        print(f"  => merged scored_{scorer}.csv: {len(all_scored)} rows")
        merged_scorers.append(scorer)

    for scorer in sorted(all_scorers - common_scorers):
        stale = target / f"scored_{scorer}.csv"
        if stale.exists():
            stale.unlink()
            print(f"  removed incomplete scored_{scorer}.csv from target")

    if not merged_scorers:
        stale_summary = target / "summary.csv"
        if stale_summary.exists():
            stale_summary.unlink()
        print("\nNo common scorers — summary.csv not regenerated.")
        return

    print()
    print("--- Regenerating summary.csv ---")
    _write_summary(str(target), merged_scorers, all_raw)
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Merge selected runs into a target run directory (in-place)"
    )
    parser.add_argument(
        "--target", required=True,
        help="Target run directory (name under results/ or full path). Modified in-place.",
    )
    parser.add_argument(
        "--sources", required=True, nargs="+",
        help="Source run directories to merge into the target (names or full paths)",
    )
    args = parser.parse_args()

    target = _resolve_run_dir(args.target)
    sources = [_resolve_run_dir(s) for s in args.sources]

    if target in sources:
        print("Error: target cannot also be a source")
        sys.exit(1)

    merge_runs(target, sources)


if __name__ == "__main__":
    main()
