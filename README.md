# Guardrail Testing of Llama-3.1-8B-Instruct

Quantization safety red-teaming pipeline. Uses [PyRIT](https://github.com/Azure/PyRIT) to automate attacks against locally-served GGUF models via llama.cpp, then independently scores each response with three different judge models to measure how quantization degrades safety guardrails. See `exploiter_plan.md` for the full research design.

## Architecture

```
llama.cpp :8080 (quantized victim)
llama.cpp :8081 (BF16 reference)
                     │
                     ▼
           LiteLLM proxy :4000
           ├─ victim-llama  → :8080
           ├─ bf16-llama    → :8081
           └─ claude-haiku-4.5 → Anthropic API
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
  scored_pyrit  scored_bf16  scored_claude
         └───────────┼───────────┘
                     ▼
                summary.csv
```

All model traffic (victim target, BF16 scorer, Claude scorer) routes through a single LiteLLM proxy. The proxy provides unified retry logic, rate limiting, and temperature control.

- **Phase 1** (`redteam.py`): PyRIT sends HarmBench objectives to the victim model via LiteLLM. All responses are saved to `raw_responses.csv`.
- **Phase 2** (`scoring.py`): Scorer models re-score every response independently and in parallel via LiteLLM. Results are written incrementally and a cross-scorer summary is generated.

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Entry point — starts LiteLLM proxy, orchestrates attack + scoring phases |
| `redteam.py` | Attack generation using PyRIT RedTeamAgent + HarmBench |
| `scoring.py` | Multi-model scoring (BF16 / Claude) |
| `litellm_proxy.py` | Shared LiteLLM proxy startup logic |
| `litellm_config.yaml` | LiteLLM proxy config (all models, retries, rate limits) |
| `patches.py` | PyRIT monkey-patches (JSON normalization) |

## Prerequisites

- **(Optional) GPU**: AMD 7900 XTX (24 GB VRAM) with ROCm 6.4+
- **Software**: Python 3.13+, [uv](https://docs.astral.sh/uv/), [llama.cpp](https://github.com/ggml-org/llama.cpp) built with ROCm/HIP/BLAS
- **API key**: Anthropic API key for Claude Haiku 4.5 scoring

## Setup

### 1. Python environment

```bash
uv sync
```

### 2. Build llama.cpp with ROCm

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100
cmake --build build --config Release -j$(nproc)
```

### 3. Download the target model

Primary model: **Llama 3.1 8B Instruct** (GGUF).
Download from HuggingFace at the desired quantization tier:

```bash
mkdir -p models
wget -O models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
```

Per the research plan, test across quantization tiers:
**Q2_K, Q3_K_M, Q4_K_M, Q5_K_M, Q6_K, Q8_0, BF16**.

### 4. Configure LiteLLM

Endpoints are defined in `src/litellm_config.yaml`. The defaults assume:
- Quantized victim at `http://127.0.0.1:8080/v1`
- BF16 reference at `http://127.0.0.1:8081/v1`

If your llama.cpp servers use different ports or model names, edit the `api_base` and `model` fields accordingly.

### 5. Set the Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or add it to a `.env` file in the project root:

```
ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

### Two-Phase GPU Workflow (recommended)

If your GPU can only hold one model at a time, run the pipeline in two phases:

**Phase A** — Quantized model on GPU, no external API needed:
```bash
# Terminal 1: Start quantized victim
./llama.cpp/build/bin/llama-server \
  -m models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf \
  --host 127.0.0.1 --port 8080 -ngl 99

# Terminal 2: Run attacks + victim self-scoring
python main.py --only-attack
```

**Phase B** — Swap to BF16 model, add Claude evaluation:
```bash
# Terminal 1: Stop quantized, start BF16
./llama.cpp/build/bin/llama-server \
  -m models/Meta-Llama-3.1-8B-Instruct-BF16.gguf \
  --host 127.0.0.1 --port 8081 -ngl 99

# Terminal 2: Re-score with BF16 + Claude
python main.py --skip-attack --latest --models bf16,claude
```

### Single-Phase Workflow

If you have enough VRAM for both models simultaneously:

```bash
# Terminal 1: Quantized victim
./llama.cpp/build/bin/llama-server \
  -m models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf \
  --host 127.0.0.1 --port 8080 -ngl 99

# Terminal 2: BF16 reference
./llama.cpp/build/bin/llama-server \
  -m models/Meta-Llama-3.1-8B-Instruct-BF16.gguf \
  --host 127.0.0.1 --port 8081 -ngl 99

# Terminal 3: Full pipeline
python main.py
```

### CLI options

| Option | Default | Description |
|---|---|---|
| `--dataset-size` | `400` | Number of HarmBench objectives |
| `--skip-attack` | off | Skip attack phase, re-score an existing run |
| `--only-attack` | off | Run attacks + victim self-scoring only (no Claude/BF16) |
| `--run-dir` | — | Path to existing run directory |
| `--latest` | off | Use the most recent run directory (with `--skip-attack`) |
| `--models` | varies | Comma-separated scorers (default depends on `--only-attack`) |
| `--victim-model` | `victim-llama` | LiteLLM model name for victim target |

### Examples

```bash
# Phase A: attacks + victim self-scoring (no Claude/BF16)
python main.py --only-attack

# Phase B: re-score latest run with BF16 + Claude
python main.py --skip-attack --latest --models bf16,claude

# Full run with all scorers (both models loaded)
python main.py

# Small test run
python main.py --dataset-size 10

# Re-score a specific run
python main.py --skip-attack --run-dir results/run_2026042714301542

# Run scoring standalone
python scoring.py --run-dir results/run_2026042714301542 --models pyrit,bf16,claude
```

Scoring is **resumable** — if interrupted, re-running the same command skips already-scored responses and continues from where it left off.

### BF16 Control Run

To establish a no-quantization baseline, attack the BF16 reference model directly:

```bash
python main.py --victim-model bf16-llama --only-attack
python main.py --skip-attack --latest --models bf16,claude
```

This attacks the full-precision model, then scores with BF16 (self-assessment) and Claude (external judge). Compare the control run's `summary.csv` against quantized runs to isolate the effect of quantization on safety guardrails.

## Output Files

Each run produces a directory under `results/`:

```
results/run_<YYYYMMDDHHMMSSmmm>/
  raw_responses.csv      All attack responses + victim model's self-assessment
  scored_pyrit.csv       Victim model's self-assessment extracted as scores
  scored_bf16.csv        Re-scored by the BF16 reference model
  scored_claude.csv      Re-scored by Claude Haiku 4.5
  summary.csv            Cross-scorer comparison table
```

### `raw_responses.csv`

| Column | Description |
|---|---|
| `objective` | The HarmBench attack objective |
| `last_response` | Full response text from the victim model |
| `strategy` | Attack strategy used (e.g. `baseline`) |
| `conversation_id` | Unique conversation identifier |
| `executed_turns` | Number of conversation turns |
| `execution_time_ms` | Attack execution time in milliseconds |
| `pyrit_outcome` | PyRIT's internal judgment (success/failure/undetermined) |
| `pyrit_outcome_reason` | Reason for PyRIT's judgment |

### `scored_<model>.csv`

| Column | Description |
|---|---|
| `objective` | The attack objective |
| `last_response` | Full response text |
| `strategy` | Attack strategy |
| `conversation_id` | Unique conversation identifier |
| `score_value` | Scorer judgment: `true`, `false`, or `error` |
| `score_rationale` | Scorer's explanation for the judgment |
| `scorer_type` | Which scorer produced this row (`pyrit`, `bf16`, or `claude`) |
| `executed_turns` | Number of conversation turns |
| `execution_time_ms` | Attack execution time |
| `pyrit_outcome` | PyRIT's internal judgment (for comparison) |

### `summary.csv`

| Metric | Description |
|---|---|
| `total` | Total responses scored |
| `success` | Count scored as attack succeeded |
| `failure` | Count scored as attack failed |
| `error` | Count where scoring produced an error |
| `undetermined` | Count with ambiguous results |
| `success_rate_pct` | Percentage of successful attacks |
| `agreement_with_claude_pct` | Agreement percentage with Claude's verdict |

Each metric row has columns for every scorer in the run (`pyrit`, `bf16`, `claude`).

## Scoring Models

| Scorer | LiteLLM Model | Description |
|---|---|---|
| `pyrit` | — | Extracts the victim model's self-assessment from Phase 1 (no LLM call). |
| `bf16` | `bf16-llama` | Full-precision (BF16) reference scorer via llama.cpp `:8081`. |
| `claude` | `claude-haiku-4.5` | Claude Haiku 4.5 as an external judge. Treated as the ground truth reference. |

All LLM scorers use `temperature=0.1` and the identical `TASK_ACHIEVED` rubric via PyRIT's `SelfAskTrueFalseScorer`.

## LiteLLM Proxy

The LiteLLM proxy is started automatically by `main.py` and manages all model traffic. Configuration in `src/litellm_config.yaml`:

| Model Name | Backend | Temperature | Rate Limit |
|---|---|---|---|
| `victim-llama` | llama.cpp `:8080` | server default | — |
| `bf16-llama` | llama.cpp `:8081` | `0.1` | — |
| `claude-haiku-4.5` | Anthropic API | `0.1` | `45 rpm` |

Global settings: `10` retries, `360s` request timeout, `120s` cooldown on failure.

# Control Results

Models Llama-3.1-8B-Instruct-BF16 and claude-haiku-4-5-20251001 are used as scorers.

Success includes content policy violation records, as an assumption is made that anything that Claude returns as a ContentPolicyViolation implies that the attack was most likely a success.

## Control Results (no prompt fuzzing) vs BF16

```
============================================
                   metric | bf16 | claude
--------------------------+-------+-------
                    total |   400 |    400
                  success |    90 |     49
                  failure |   310 |    351
                    error |     0 |      0
             undetermined |     0 |      0
 content_policy_violation |     0 |      1
         success_rate_pct |  22.5 |  12.25
             cpv_rate_pct |   0.0 |   2.04
agreement_with_claude_pct | 72.25 |  100.0
```

## Control Results (no prompt fuzzing) vs Q8_0

Q8_0 run with cross-scorer comparison (400 HarmBench objectives):

```
=================================================
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

## Control Results (no prompt fuzzing) vs Q4_K_M

```
===================================================
                   metric | q4_k_m|  bf16 | claude
--------------------------+-------+-------+-------
                    total |   400 |   400 |    400
                  success |   162 |    81 |     50
                  failure |   238 |   319 |    350
                    error |     0 |     0 |      0
             undetermined |     0 |     0 |      0
 content_policy_violation |     0 |     0 |      0
         success_rate_pct |  40.5 | 20.25 |   12.5
             cpv_rate_pct |   0.0 |   0.0 |    0.0
agreement_with_claude_pct |  58.0 | 73.75 |  100.0
```