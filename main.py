import argparse
import asyncio
import csv
from pathlib import Path

import src.litellm_proxy as litellm_proxy
import src.patches  # noqa: F401
import src.redteam as redteam
import src.scoring as scoring
from src.config import RESULTS_DIR
from src.scorers import DEFAULT_MODELS


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


def _build_victim_block(tier: str | None, victim_model_name: str, config_path: str | None) -> dict | None:
    """Victim provenance block from --tier, or None when no tier given."""
    if not tier:
        return None
    from src import tiers
    from src.victim_meta import build_victim_block

    config = tiers.load_config(config_path) if config_path else tiers.load_config()
    gguf = tiers.resolve_gguf(tier.upper(), config)
    return build_victim_block(tier.upper(), gguf, config.get("model_name", ""),
                              litellm_model=victim_model_name)


async def _run(args: argparse.Namespace, run_dir: str | None, models: list[str]) -> None:
    """Attack phase (unless skipped) + scoring phase for the CLI workflow."""
    if not args.skip_attack:
        print("=" * 60)
        print("PHASE 1: Running attacks")
        print("=" * 60)
        victim = _build_victim_block(args.tier, args.victim_model, args.config)
        run_name = await redteam.run_attacks(
            dataset_size=args.dataset_size, victim_model_name=args.victim_model,
            tier=args.tier.upper() if args.tier else None, victim=victim,
        )
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
    parser.add_argument("--tier", type=str, default=None, help="Quantization tier of the victim (e.g. Q8_0, Q4_K_M, BF16): required for --e2e; for attacks it records victim provenance (model, GGUF, SHA-256) in meta.json")
    parser.add_argument("--e2e", action="store_true", help="End-to-end: auto-manage llama.cpp servers and run all phases for a tier")
    parser.add_argument("--config", type=str, default=None, help="Path to e2e config YAML (default: src/e2e_config.yaml)")
    args = parser.parse_args()

    if args.e2e:
        if args.skip_attack or args.only_attack:
            parser.error("--e2e is mutually exclusive with --skip-attack and --only-attack")
        if not args.tier:
            parser.error("--tier is required with --e2e")
        from src import tiers
        from src.e2e import run_e2e
        config_path = args.config or tiers.DEFAULT_CONFIG
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
        asyncio.run(_run(args, run_dir, models))
    finally:
        if proxy_proc is not None:
            proxy_proc.terminate()


if __name__ == "__main__":
    main()
