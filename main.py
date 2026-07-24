import argparse
import asyncio
import csv
from pathlib import Path

import src.patches  # noqa: F401
import src.litellm_proxy as litellm_proxy
import src.redteam as redteam
import src.scoring as scoring
from src.config import DEFAULT_MODELS, RESULTS_DIR


def _find_latest_run() -> str | None:
    runs = sorted(RESULTS_DIR.glob("run_*"))
    if not runs:
        return None
    return str(runs[-1])


def _print_summary_table(run_dir: str) -> None:
    """Render summary.csv as a plain-text box table (matches make_tables style)."""
    summary_path = Path(run_dir) / "summary.csv"
    if not summary_path.exists():
        print("  No summary.csv found")
        return

    with open(summary_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    import make_tables
    print(make_tables._fmt_box(rows))


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
    _print_summary_table(run_dir)


def main():
    parser = argparse.ArgumentParser(description="Run red-team attacks and multi-model scoring")
    parser.add_argument("--dataset-size", type=int, default=400, help="Number of attack objectives (default: 400)")
    parser.add_argument("--skip-attack", action="store_true", help="Skip attack phase, re-score existing run")
    parser.add_argument("--run-dir", type=str, default=None, help="Path to existing run dir (required with --skip-attack unless --latest)")
    parser.add_argument("--latest", action="store_true", help="Use the most recent run directory (with --skip-attack)")
    parser.add_argument("--only-attack", action="store_true", help="Run attacks + victim self-scoring only (no Claude/BF16)")
    parser.add_argument("--models", default=None, help="Comma-separated scorers (default: asr_pyrit for --only-attack, else all). Also available: strict_pyrit,lenient_pyrit")
    parser.add_argument("--victim-model", type=str, default="victim-llama", help="LiteLLM model name for victim target (default: victim-llama)")
    parser.add_argument("--e2e", action="store_true", help="End-to-end: auto-manage llama.cpp servers and run all phases for a tier")
    parser.add_argument("--tier", type=str, default=None, help="Quantization tier for --e2e (e.g. Q8_0, Q4_K_M, BF16)")
    parser.add_argument("--config", type=str, default=None, help="Path to e2e config YAML (default: src/e2e_config.yaml)")
    args = parser.parse_args()

    if args.e2e:
        if args.skip_attack or args.only_attack:
            parser.error("--e2e is mutually exclusive with --skip-attack and --only-attack")
        if not args.tier:
            parser.error("--tier is required with --e2e")
        from src.e2e import run_e2e, DEFAULT_CONFIG
        config_path = args.config or DEFAULT_CONFIG
        asyncio.run(run_e2e(args.tier, args.dataset_size, config_path))
        return

    if args.only_attack and args.skip_attack:
        parser.error("--only-attack and --skip-attack are mutually exclusive")

    if args.models is not None:
        models = [m.strip() for m in args.models.split(",")]
    elif args.only_attack:
        models = ["asr_pyrit"]
    else:
        models = list(DEFAULT_MODELS)

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
