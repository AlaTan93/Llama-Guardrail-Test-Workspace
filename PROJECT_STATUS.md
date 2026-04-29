# Project Status: Quantization Safety Red-Teaming Pipeline

## Project Overview

Automated red-teaming pipeline using PyRIT to test quantized GGUF models served via llama.cpp for safety guardrail degradation. The pipeline attacks a locally-served model with harmful objectives from HarmBench, scores responses for safety compliance using Claude Haiku 4.5 via LiteLLM proxy, and exports structured CSV results per run.

Full research design is documented in `exploiter_plan.md`.

## Architecture

```
llama.cpp server (victim model, OpenAI-compatible API)
        |
        v
  PyRIT RedTeamAgent
  - HarmBench dataset (400 objectives)
  - Baseline / attack strategies
        |
        v
  LiteLLM proxy (port 4000)
        |
        v
  Claude Haiku 4.5 (safety scorer, temperature 0.1)
```

- **Victim target**: `OpenAIChatTarget` pointing at llama.cpp server (configured via `.pyrit/.env`)
- **Scorer**: `SelfAskTrueFalseScorer` with `TrueFalseQuestionPaths.TASK_ACHIEVED` rubric, routed through LiteLLM to Anthropic API
- **Dataset**: HarmBench (fetched via `SeedDatasetProvider`)
- **Storage**: In-memory (non-persistent)
- **Results**: CSV export to `results/<animal>_<timestamp>/`

## What Has Been Done

### Infrastructure

- Project scaffolded with `uv`, Python 3.13, `pyrit>=0.12.1`, `litellm[proxy]==1.83.7`
- LiteLLM proxy config (`litellm_config.yaml`) with Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Proxy auto-start with health check and 60s timeout in `redteam.py`
- Environment config in `.pyrit/.env` for victim target endpoint

### Main Script (`redteam.py`)

- PyRIT initialization with in-memory database
- HarmBench dataset loading with configurable `max_dataset_size`
- `RedTeamAgent` with `AttackScoringConfig` using `SelfAskTrueFalseScorer`
- `scenario_strategies` list ready for PAIR, Crescendo, etc. (currently empty = baseline only)
- Console summary output via `ConsoleScenarioResultPrinter`

### CSV Result Export

Results written to `results/<animal><YYYYMMDDHHMMSSmmm>/` with four files per run:

| File | Contents |
|---|---|
| `successes.csv` | Attacks where objective was achieved (model complied) |
| `failures.csv` | Attacks that failed (model refused or scorer judged non-compliant) |
| `undetermined.csv` | Ambiguous/undetermined outcomes |
| `statistics.csv` | Single-row summary: counts, rates, averages, strategies used |

Result CSV columns: `objective`, `outcome`, `outcome_reason`, `executed_turns`, `execution_time_ms`, `conversation_id`, `last_response`, `strategy`

Statistics CSV columns: `run_name`, `datetime`, `total_attacks`, `successes`, `failures`, `undetermined`, `success_rate_pct`, `failure_rate_pct`, `undetermined_rate_pct`, `avg_execution_time_ms`, `avg_turns`, `strategies_used`

### Bug Fixes

- Fixed `TrueFalseQuestionPaths.TASK_ACHIEVED` type mismatch: enum member returns `TrueFalseQuestionPaths` not `Path` — added `.value` to extract the underlying `PosixPath`
- Fixed LiteLLM model ID: `anthropic/claude-3-5-haiku-20241022` (old, unavailable) → `anthropic/claude-haiku-4-5-20251001` (matches API key's available models)
- Fixed scorer temperature consistency: all scorer models (BF16, Claude) now explicitly use `temperature=0.1` via `OpenAIChatTarget` constructor, ensuring deterministic and comparable scoring

### BF16 Control Run Support

Added `--victim-endpoint` and `--victim-model` CLI args to `main.py`, allowing the attack target to be overridden without editing `.pyrit/.env`. This enables BF16 control runs:

```bash
python main.py --victim-endpoint http://127.0.0.1:8081/v1 --models bf16,claude
```

The control attacks the full-precision model, scored by BF16 (self-assessment) and Claude (external judge), producing a no-quantization baseline for comparison.

### Verified End-to-End

Confirmed working with 10-objective baseline run:
- 2 successes, 8 failures, 0 undetermined
- 20% baseline success rate against victim model
- All CSV files populated correctly

## Results

First completed Q8_0 run with cross-scorer comparison (400 HarmBench objectives):

```
============================================================
                   metric | q8_0 | bf16 | claude
--------------------------+------+------+-------
                    total |  400 |  400 |    400
                  success |   94 |   92 |     56
                  failure |  306 |  308 |    344
                    error |    0 |    0 |      0
             undetermined |    0 |    0 |      0
 content_policy_violation |    0 |    0 |      1
         success_rate_pct | 23.5 | 23.0 |   14.0
             cpv_rate_pct |  0.0 |  0.0 |   1.79
agreement_with_claude_pct | 73.5 | 74.0 |  100.0
```

## Current Limitations

- **Single strategy**: Only baseline (unmodified prompts) tested; no adversarial attack strategies active
- **Single model**: Only one model family at one quantization level
- **No persistence**: In-memory database; results only survive via CSV export
- **No capability baseline**: No MMLU or general benchmark comparison to separate safety degradation from general quality loss
- **Scorer rubric**: Using `TASK_ACHIEVED`; not yet tested with `TASK_ACHIEVED_REFINED`
- **Temperature**: Victim server temperature not yet tuned for reproducibility vs. realism tradeoff
- **Concurrency**: Hardcoded `max_concurrency=20`; not tuned for GPU throughput

## Future Suggestions

### Short-Term (Pipeline Improvements)

- **Add attack strategies**: Populate `scenario_strategies` with PAIR, Crescendo, GCG transfer, multi-turn attacks
- **Skip baseline on repeat runs**: Use `include_baseline=False` in `RedTeamAgent` when baseline is already measured
- **Persistent database**: Switch from `IN_MEMORY` to SQLite for result storage across runs
- **Victim temperature control**: Parameterize victim server temperature (0.1 for reproducibility, 0.8 for realism)
- **Configurable dataset size**: Expose `max_dataset_size` as CLI argument or config file parameter

### Medium-Term (Experiment Expansion)

- **Multi-model loop**: Iterate over Llama 3.1 8B, Qwen 2.5 7B, Mistral 7B v0.3
- **Multi-quantization loop**: Test Q2_K, Q3_K_M, Q4_K_M, Q5_K_M, Q6_K, Q8_0, FP16 for each model
- **Additional datasets**: StrongREJECT (313 prompts), XSTest (250 safe prompts for over-refusal measurement)
- **Better scoring**: Add WildGuard-7B or HarmBench fine-tuned classifier as secondary scorer
- **Custom scorer**: Combine multiple evaluation signals into a single scoring pass

### Long-Term (Research Outputs)

- **Pre-register hypotheses**: Document specific predictions before running experiments (e.g., "Q3_K_M will show >15% higher ASR than Q8_0")
- **Statistical analysis**: McNemar's test for ASR comparisons, Wilcoxon signed-rank for continuous scores, Wilson score intervals
- **Mechanistic analysis**: Activation probing on safety-relevant prompts at different quantization levels
- **Mitigation testing**: Evaluate whether external guardrails (LlamaGuard, WildGuard) compensate for quantization-induced safety loss
- **Safety-vs-capability asymmetry**: Pair safety metrics with capability benchmarks to show whether safety degrades faster
- **arXiv paper**: 10-12 page workshop-format paper targeting NeurIPS ML Safety Workshop, SaTML, or ICML
- **Alignment Forum post**: Narrative version highlighting deployment implications
- **Per-category vulnerability breakdowns**: Heatmaps of ASR across quantization x attack type x model x harm category
