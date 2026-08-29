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

import src.redteam as redteam
import src.scoring as scoring
from src import tiers
from src.config import RESULTS_DIR
from src.csv_io import load_raw_responses
from src.run_meta import update_meta
from src.scorers import PHASE_A_MODELS, PHASE_B_CONTROL, PHASE_B_QUANT
from src.servers import ServerStack
from src.summaries import write_summaries
from src.victim_meta import build_victim_block


async def run_e2e(
    tier: str,
    dataset_size: int = 400,
    config_path: str = tiers.DEFAULT_CONFIG,
    progress=None,
) -> None:
    """Full pipeline for one tier.

    *progress* (optional) is a :class:`src.progress.ProgressReporter`
    forwarded to the attack and scoring phases.
    """
    config = tiers.load_config(config_path)
    is_control = tier.upper() == "BF16"

    phase_b_models = list(PHASE_B_CONTROL if is_control else PHASE_B_QUANT)
    all_models = list(PHASE_A_MODELS) + phase_b_models

    print("=" * 60)
    print(f"E2E run  |  tier={tier}  |  dataset_size={dataset_size}")
    if is_control:
        print("(BF16 control run -- asr_bf16/strict_bf16/lenient_bf16 judges skipped)")
    print("=" * 60)

    # The proxy is held across both GPU phases; each llama server only for its
    # own phase (single-GPU schedule: victim and BF16 judges never coexist).
    async with ServerStack(config, proxy=True):
        # -- Phase A --
        print("\n" + "=" * 60)
        print("PHASE A: Attacks + victim self-scoring")
        print("=" * 60)

        async with ServerStack(config, victim_tier=tier, proxy=False):
            victim_gguf = tiers.resolve_gguf(tier, config)
            model_name = config.get("model_name", "")
            victim = (
                await asyncio.to_thread(build_victim_block, tier, victim_gguf, model_name)
                if model_name
                else None
            )

            run_name = await redteam.run_attacks(
                dataset_size=dataset_size, tier=tier, victim=victim, progress=progress
            )
            run_dir = str(RESULTS_DIR / run_name)

            responses = load_raw_responses(run_dir)
            print(f"Loaded {len(responses)} responses from {run_dir}")

            # Victim self-scores: ASR (extraction) + refusal (live judge via :8080).
            scoring.score_pyrit_outcomes(responses, run_dir, progress=progress)
            await asyncio.gather(
                scoring.score_responses(responses, "strict_pyrit", run_dir, progress=progress),
                scoring.score_responses(responses, "lenient_pyrit", run_dir, progress=progress),
            )

        # -- Phase B --
        print("\n" + "=" * 60)
        print("PHASE B: External scoring")
        print("=" * 60)

        async with ServerStack(config, bf16=not is_control, proxy=False):
            tasks = [scoring.score_responses(responses, m, run_dir, progress=progress)
                     for m in phase_b_models]
            await asyncio.gather(*tasks)

    # -- Summaries --
    print("\n" + "=" * 60)
    print("Writing summaries")
    print("=" * 60)
    write_summaries(run_dir, all_models, responses)
    update_meta(run_dir, status="complete")

    print(f"\nE2E complete.  Results: {run_dir}")
    print(f"  python make_tables.py --run-dir {run_dir}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="End-to-end pipeline with server management")
    parser.add_argument("--tier", required=True, help="Quantization tier (e.g. Q8_0, Q4_K_M, BF16)")
    parser.add_argument("--dataset-size", type=int, default=400, help="Number of HarmBench objectives")
    parser.add_argument("--config", default=tiers.DEFAULT_CONFIG, help="Path to e2e config YAML")
    args = parser.parse_args()

    asyncio.run(run_e2e(args.tier, args.dataset_size, args.config))


if __name__ == "__main__":
    main()
