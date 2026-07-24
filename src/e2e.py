"""End-to-end pipeline orchestrator.

Manages llama.cpp server lifecycle and sequences the two GPU phases:

  Phase A (victim on GPU):
    1. start llama-server <tier>.gguf -> :8080
    2. run attacks  (objective_scorer captures ASR / pyrit_outcome)
    3. score asr_pyrit (extract) + strict_pyrit + lenient_pyrit (live judge via :8080)
    4. stop :8080

  Phase B (BF16 reference on GPU, or API-only for control run):
    5. start llama-server BF16.gguf -> :8081   (skipped for BF16 control run)
    6. score asr_bf16, asr_claude, strict_bf16, strict_claude, lenient_bf16, lenient_claude
       (control run: asr_claude, strict_claude, lenient_claude only -- bf16 judge == victim)
    7. stop :8081

    8. write_summaries -> summary.csv + summary_refusal.csv + summary_crosstab.csv
"""

import asyncio
from pathlib import Path

import yaml

from src.config import (
    PHASE_A_MODELS,
    PHASE_B_CONTROL,
    PHASE_B_QUANT,
    RESULTS_DIR,
)
from src.csv_io import load_raw_responses
import src.llama_server as llama_server
import src.litellm_proxy as litellm_proxy
import src.redteam as redteam
import src.scoring as scoring
from src.summaries import write_summaries

DEFAULT_CONFIG = str(Path(__file__).parent / "e2e_config.yaml")


def load_config(config_path: str = DEFAULT_CONFIG) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_gguf(tier: str, config: dict) -> str:
    tiers = config.get("tiers", {})
    if tier not in tiers:
        available = ", ".join(sorted(tiers))
        raise ValueError(f"Unknown tier '{tier}'. Available: {available}")
    models_dir = Path(config.get("models_dir", "./models"))
    gguf = str(models_dir / tiers[tier])
    if not Path(gguf).exists():
        raise FileNotFoundError(f"GGUF not found: {gguf}")
    return gguf


async def run_e2e(
    tier: str,
    dataset_size: int = 400,
    config_path: str = DEFAULT_CONFIG,
) -> None:
    config = load_config(config_path)
    ports = config["ports"]
    is_control = tier.upper() == "BF16"

    victim_gguf = _resolve_gguf(tier, config)
    phase_b_models = list(PHASE_B_CONTROL if is_control else PHASE_B_QUANT)
    all_models = list(PHASE_A_MODELS) + phase_b_models

    print("=" * 60)
    print(f"E2E run  |  tier={tier}  |  dataset_size={dataset_size}")
    if is_control:
        print("(BF16 control run -- asr_bf16/strict_bf16/lenient_bf16 judges skipped)")
    print("=" * 60)

    proxy_proc = None
    victim_proc = None
    bf16_proc = None

    try:
        # LiteLLM proxy stays up across both phases (routes victim/bf16/claude).
        proxy_proc = litellm_proxy.start_litellm_proxy()

        # -- Phase A --
        print("\n" + "=" * 60)
        print("PHASE A: Attacks + victim self-scoring")
        print("=" * 60)

        victim_proc = llama_server.start_server(victim_gguf, ports["victim"], config)

        run_name = await redteam.run_attacks(dataset_size=dataset_size)
        run_dir = str(RESULTS_DIR / run_name)

        responses = load_raw_responses(run_dir)
        print(f"Loaded {len(responses)} responses from {run_dir}")

        # Victim self-scores: ASR (extraction) + refusal (live judge via :8080).
        scoring.score_pyrit_outcomes(responses, run_dir)
        await asyncio.gather(
            scoring.score_responses(responses, "strict_pyrit", run_dir),
            scoring.score_responses(responses, "lenient_pyrit", run_dir),
        )

        llama_server.stop_server(victim_proc, config)
        victim_proc = None

        # -- Phase B --
        print("\n" + "=" * 60)
        print("PHASE B: External scoring")
        print("=" * 60)

        if not is_control:
            bf16_gguf = _resolve_gguf("BF16", config)
            bf16_proc = llama_server.start_server(bf16_gguf, ports["bf16"], config)

        tasks = [scoring.score_responses(responses, m, run_dir) for m in phase_b_models]
        await asyncio.gather(*tasks)

        if bf16_proc is not None:
            llama_server.stop_server(bf16_proc, config)
            bf16_proc = None

        # -- Summaries --
        print("\n" + "=" * 60)
        print("Writing summaries")
        print("=" * 60)
        write_summaries(run_dir, all_models, responses)

        print(f"\nE2E complete.  Results: {run_dir}")
        print(f"  python make_tables.py --run-dir {run_dir}")

    finally:
        if bf16_proc is not None:
            llama_server.stop_server(bf16_proc, config)
        if victim_proc is not None:
            llama_server.stop_server(victim_proc, config)
        if proxy_proc is not None:
            proxy_proc.terminate()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="End-to-end pipeline with server management")
    parser.add_argument("--tier", required=True, help="Quantization tier (e.g. Q8_0, Q4_K_M, BF16)")
    parser.add_argument("--dataset-size", type=int, default=400, help="Number of HarmBench objectives")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to e2e config YAML")
    args = parser.parse_args()

    asyncio.run(run_e2e(args.tier, args.dataset_size, args.config))


if __name__ == "__main__":
    main()
