# ollama-test-1

Quantization safety red-teaming pipeline. Uses [PyRIT](https://github.com/Azure/PyRIT) to automate attacks against locally-served GGUF models via llama.cpp, then independently scores each response with three different judge models to measure how quantization degrades safety guardrails. See `exploiter_plan.md` for the full research design.

## Architecture

```
llama.cpp :8080 (quantized victim)  ←  PyRIT attacks  ←  HarmBench
                     │
                     ▼
              raw_responses.csv
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
   :8080 self    :8081 bf16    LiteLLM → Claude Haiku 4.5
       ▼             ▼             ▼
 scored_self    scored_bf16   scored_claude
       └─────────────┼─────────────┘
                     ▼
                summary.csv
```

- **Phase 1** (`redteam.py`): PyRIT sends HarmBench objectives to the victim model. All responses are saved to `raw_responses.csv`.
- **Phase 2** (`scoring.py`): Three scorer models re-score every response independently and in parallel. Results are written incrementally and a cross-scorer summary is generated.

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Entry point — orchestrates attack + scoring phases |
| `redteam.py` | Attack generation using PyRIT RedTeamAgent + HarmBench |
| `scoring.py` | Multi-model scoring (self / BF16 / Claude) |
| `litellm_config.yaml` | LiteLLM proxy config (Claude Haiku 4.5, retries, rate limits) |
| `.pyrit/.env` | Victim model endpoint configuration |

## Prerequisites

- **GPU**: AMD 7900 XTX (24 GB VRAM) with ROCm 6.4+
- **Software**: Python 3.13+, [uv](https://docs.astral.sh/uv/), [llama.cpp](https://github.com/ggml-org/llama.cpp) built with ROCm/HIP
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

### 4. Configure the victim endpoint

Edit `.pyrit/.env`:

```
OPENAI_CHAT_ENDPOINT="http://127.0.0.1:8080/v1"
OPENAI_CHAT_KEY="not-needed"
OPENAI_CHAT_MODEL="llama3"
```

The `OPENAI_CHAT_MODEL` value must match the model name the server
reports — check with `curl http://127.0.0.1:8080/v1/models`.

### 5. Set the Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or add it to a `.env` file in the project root:

```
ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

### Start the llama.cpp servers

You need two llama.cpp instances running — one for the quantized victim (and self-scoring) and one for the BF16 reference scorer:

```bash
# Terminal 1: Quantized model (victim + self-scorer)
./llama.cpp/build/bin/llama-server \
  -m models/meta-llama-Llama-3.1-8B-Instruct-Q8_0.gguf \
  --host 127.0.0.1 --port 8080 -ngl 99

# Terminal 2: BF16 reference model (scorer)
./llama.cpp/build/bin/llama-server \
  -m models/Meta-Llama-3.1-8B-Instruct-BF16.gguf \
  --host 127.0.0.1 --port 8081 -ngl 99
```

### Run the full pipeline

```bash
python main.py
```

This runs both phases: attack generation followed by scoring with all three models.

### CLI options

| Option | Default | Description |
|---|---|---|
| `--dataset-size` | `400` | Number of HarmBench objectives |
| `--skip-attack` | off | Skip attack phase, re-score an existing run |
| `--run-dir` | — | Path to existing run directory (required with `--skip-attack`) |
| `--models` | `pyrit,bf16,claude` | Which scorer models to use |
| `--victim-model` | `llama3` | Override victim model name |

### Examples

```bash
# Full run with default settings (400 objectives, all 3 scorers)
python main.py

# Small test run
python main.py --dataset-size 10

# Re-score an existing run (e.g. after a crash)
python main.py --skip-attack --run-dir results/run_2026042714301542

# Only BF16 and Claude scoring (skip pyrit extraction)
python main.py --models bf16,claude

# Run scoring standalone
python scoring.py --run-dir results/run_2026042714301542 --models pyrit,bf16,claude
```

Scoring is **resumable** — if interrupted, re-running the same command skips already-scored responses and continues from where it left off.

## Output Files

Each run produces a directory under `results/`:

```
results/run_<YYYYMMDDHHMMSSmmm>/
  raw_responses.csv      All attack responses + PyRIT internal outcome
  scored_self.csv        Re-scored by the quantized model itself
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
| `scorer_type` | Which scorer produced this row (`self`, `bf16`, or `claude`) |
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

Each metric row has columns for every scorer (`self`, `bf16`, `claude`, `pyrit`).

## Scoring Models

| Scorer | Endpoint | Description |
|---|---|---|
| `self` | llama.cpp `:8080` | The same quantized model scores its own responses. At low quantization (e.g. Q2_K), self-scoring may produce garbage — that is itself a research finding. |
| `bf16` | llama.cpp `:8081` | Full-precision (BF16) reference scorer. Provides a high-quality local baseline without external API dependency. |
| `claude` | LiteLLM `:4000` → Anthropic | Claude Haiku 4.5 as an external judge. Treated as the ground truth reference for cross-scorer agreement metrics. |

All three scorers use the identical `TASK_ACHIEVED` rubric via PyRIT's `SelfAskTrueFalseScorer`, ensuring results are directly comparable.

## LiteLLM Proxy

The LiteLLM proxy is started automatically when Claude scoring is needed. Configuration in `litellm_config.yaml`:

- **Model**: `anthropic/claude-haiku-4-5-20251001`
- **Temperature**: `0.1` (deterministic scoring)
- **Rate limit**: `45 rpm`
- **Retries**: `10` attempts with `120s` cooldown on failure

## Control Results (no prompt fuzzing) vs q8_0

Models Llama-3.1-8B-Instruct-BF16 and claude-haiku-4-5-20251001 are used as scorers.

Q8_0 run with cross-scorer comparison (400 HarmBench objectives):

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
