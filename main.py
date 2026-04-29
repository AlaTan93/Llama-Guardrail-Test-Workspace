import argparse
import asyncio
import csv
from pathlib import Path

import src.patches  # noqa: F401
import src.litellm_proxy as litellm_proxy
import src.redteam as redteam
import src.scoring as scoring

RESULTS_DIR = Path(__file__).parent / "results"


def _find_latest_run() -> str | None:
    runs = sorted(RESULTS_DIR.glob("run_*"))
    if not runs:
        return None
    return str(runs[-1])


async def _run(dataset_size: int, skip_attack: bool, run_dir: str | None, models: list[str], victim_model_name: str) -> None:
    if not skip_attack:
        print("=" * 60)
        print("PHASE 1: Running attacks")
        print("=" * 60)
        run_name = await redteam.run_attacks(dataset_size=dataset_size, victim_model_name=victim_model_name)
        run_dir = str(RESULTS_DIR / run_name)
    else:
        if not run_dir:
            print("Error: --run-dir or --latest is required when using --skip-attack")
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
    parser.add_argument("--run-dir", type=str, default=None, help="Path to existing run dir (required with --skip-attack unless --latest)")
    parser.add_argument("--latest", action="store_true", help="Use the most recent run directory (with --skip-attack)")
    parser.add_argument("--only-attack", action="store_true", help="Run attacks + victim self-scoring only (no Claude/BF16)")
    parser.add_argument("--models", default=None, help="Comma-separated scorers (default: pyrit,victim for --only-attack, else pyrit,victim,bf16,claude)")
    parser.add_argument("--victim-model", type=str, default="victim-llama", help="LiteLLM model name for victim target (default: victim-llama)")
    args = parser.parse_args()

    if args.only_attack and args.skip_attack:
        parser.error("--only-attack and --skip-attack are mutually exclusive")

    if args.models is not None:
        models = [m.strip() for m in args.models.split(",")]
    elif args.only_attack:
        models = ["pyrit"]
    else:
        models = ["pyrit", "bf16", "claude"]

    run_dir = args.run_dir
    if args.latest:
        run_dir = _find_latest_run()
        if run_dir is None:
            print("Error: no runs found in results/")
            return

    proxy_proc = litellm_proxy.start_litellm_proxy()
    try:
        asyncio.run(_run(args.dataset_size, args.skip_attack, run_dir, models, args.victim_model))
    finally:
        if proxy_proc is not None:
            proxy_proc.terminate()


if __name__ == "__main__":
    main()
