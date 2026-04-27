import argparse
import asyncio
import csv
from pathlib import Path

import src.redteam as redteam
import src.scoring as scoring


async def _run(dataset_size: int, skip_attack: bool, run_dir: str | None, models: list[str]) -> None:
    if not skip_attack:
        print("=" * 60)
        print("PHASE 1: Running attacks")
        print("=" * 60)
        run_name = await redteam.run_attacks(dataset_size=dataset_size)
        run_dir = str(Path(__file__).parent / "results" / run_name)
    else:
        if not run_dir:
            print("Error: --run-dir is required when using --skip-attack")
            return
        print(f"Skipping attack phase. Using existing run: {run_dir}")

    print("\n" + "=" * 60)
    print("PHASE 2: Scoring responses")
    print("=" * 60)
    await scoring.run_scoring(run_dir, models=models)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    summary_path = Path(run_dir) / "summary.csv"
    if summary_path.exists():
        with open(summary_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        headers = list(rows[0].keys())
        col_widths = {h: max(len(h), max(len(str(r.get(h, ""))) for r in rows)) for h in headers}

        header_line = " | ".join(h.rjust(col_widths[h]) for h in headers)
        sep_line = "-+-".join("-" * col_widths[h] for h in headers)
        print(header_line)
        print(sep_line)
        for r in rows:
            line = " | ".join(str(r.get(h, "")).rjust(col_widths[h]) for h in headers)
            print(line)
    else:
        print("  No summary.csv found")


def main():
    parser = argparse.ArgumentParser(description="Run red-team attacks and multi-model scoring")
    parser.add_argument("--dataset-size", type=int, default=400, help="Number of attack objectives (default: 400)")
    parser.add_argument("--skip-attack", action="store_true", help="Skip attack phase, re-score existing run")
    parser.add_argument("--run-dir", type=str, default=None, help="Path to existing run dir (required with --skip-attack)")
    parser.add_argument("--models", default="self,bf16,claude", help="Comma-separated scorers: self,bf16,claude (default: all)")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    asyncio.run(_run(args.dataset_size, args.skip_attack, args.run_dir, models))


if __name__ == "__main__":
    main()
