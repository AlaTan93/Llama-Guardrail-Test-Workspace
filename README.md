# WIP UPDATE

Methodology has been changed, data needs to be updated.

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
   scored_asr_pyrit  scored_asr_bf16  scored_asr_claude
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
| `make_tables.py` | Render a run's summary CSVs as markdown comparison tables |
| `merge_runs.py` | Merge multiple run directories into a target run |
| `ARCHITECTURE.md` | Layer/module map, run data-flow, job lifecycle, container topology |
| `src/config.py` | Paths, service hosts, CSV schemas |
| `src/scorers.py` | Judge × rubric registry (all scorers + model groups) |
| `src/tiers.py` | Tier → GGUF / docker-image resolution (single home) |
| `src/progress.py` | `ProgressReporter` protocol for pipeline progress |
| `src/e2e.py` | Two-phase end-to-end orchestrator (per tier) |
| `src/redteam.py` | PyRIT attack orchestration (new runs + re-attacks) |
| `src/runs_io.py` | Run persistence: writing/merging raw responses + meta |
| `src/scoring.py` | Judge loops, retry/error handling, invalidation, resume |
| `src/judges.py` | PyRIT scorer construction (via LiteLLM) + JSON sanitisation |
| `src/summaries.py` | Summary CSV generation (ASR, refusal, crosstab) |
| `src/metrics.py` | Score-counting, agreement, F1, and crosstab computation |
| `src/servers.py` | `ServerStack`: llama.cpp + LiteLLM lifecycle in one place |
| `src/llama_server.py` | llama.cpp launch primitives (local binary or docker) |
| `src/litellm_proxy.py` | LiteLLM proxy bring-up (spawn or external/compose) |
| `src/run_meta.py` | Per-run `meta.json` (status, notes) |
| `src/victim_meta.py` | Victim provenance block + cached GGUF SHA-256 |
| `src/csv_io.py` | Shared CSV read/write/row-surgery helpers |
| `src/http_health.py` | Shared HTTP health-check |
| `src/json_sanitize.py` | JSON response sanitisation for judge output |
| `src/patches.py` | PyRIT monkey-patches (JSON normalization) |
| `src/e2e_config.yaml` | Tiers, server mode (docker/local), pinned llama.cpp images |
| `src/litellm_config.yaml` | LiteLLM proxy config (all models, retries, rate limits) |
| `src/web/` | Dashboard backend (FastAPI app, auth, job manager, runners, views) |
| `Dockerfile` | Multi-stage web image (SPA build + python runtime, all pins frozen) |
| `docker-compose.yml` | Full containerised stack (web + litellm; llama.cpp launched dynamically) |
| `frontend/` | Web dashboard SPA (React + TS + Vite + Tailwind; built via Docker) |
| `scripts/build_frontend.sh` | Containerised frontend build (host needs only Docker) |
| `scripts/dev_frontend.sh` | Containerised vite dev server |
| `tests/` | Pytest suite (CSV surgery, subset scoring, views, API) |

## Prerequisites

- **GPU (optional for orchestration)**: AMD 7900 XTX (24 GB VRAM) — ROCm userspace ships inside the pinned llama.cpp container; the host only needs the `amdgpu` kernel driver (`/dev/kfd`, `/dev/dri`)
- **Software**: Docker + Docker Compose (containerised stack), or Python 3.13+ with [uv](https://docs.astral.sh/uv/) for host-mode runs (host-mode GPU serving additionally requires a local [llama.cpp](https://github.com/ggml-org/llama.cpp) build)
- **API keys**: AWS credentials for Claude Haiku 4.5 via Bedrock (primary); Anthropic API key as fallback

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

### 5. Set API credentials

Claude Haiku 4.5 scores via AWS Bedrock (primary) with Anthropic direct API as
fallback. Both sets of credentials are needed:

```bash
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION_NAME="us-east-1"
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or add them to a `.env` file in the project root (see `.env.template`).

Enable Claude Haiku 4.5 model access in your AWS account under Bedrock before
the first run.

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
| `--models` | varies | Comma-separated scorers (default depends on `--only-attack`). Available: `asr_pyrit,asr_bf16,asr_claude,strict_bf16,strict_claude,strict_pyrit,lenient_claude,lenient_bf16,lenient_pyrit` |
| `--victim-model` | `victim-llama` | LiteLLM model name for victim target |

### Examples

```bash
# Phase A: attacks + victim self-scoring (no Claude/BF16)
python main.py --only-attack

# Phase B: re-score latest run with BF16 + Claude (ASR + refusal)
python main.py --skip-attack --latest --models asr_bf16,asr_claude,strict_bf16,strict_claude

# Phase B: refusal-only rescore of an existing run (no attack re-run needed)
python main.py --skip-attack --latest --models strict_claude,strict_bf16

# Full run with all scorers (both models loaded)
python main.py

# Small test run
python main.py --dataset-size 10

# Re-score a specific run
python main.py --skip-attack --run-dir results/run_2026042714301542

# Run scoring standalone
python scoring.py --run-dir results/run_2026042714301542 --models asr_pyrit,asr_bf16,asr_claude,strict_bf16,strict_claude
```

Scoring is **resumable** — if interrupted, re-running the same command skips already-scored responses and continues from where it left off.

### BF16 Control Run

To establish a no-quantization baseline, attack the BF16 reference model directly:

```bash
python main.py --victim-model bf16-llama --only-attack
python main.py --skip-attack --latest --models asr_bf16,asr_claude,strict_bf16,strict_claude
```

This attacks the full-precision model, then scores with BF16 (self-assessment) and Claude (external judge). Compare the control run's `summary.csv` and `summary_refusal.csv` against quantized runs to isolate the effect of quantization on safety guardrails.

## Output Files

Each run produces a directory under `results/`:

```
results/run_<YYYYMMDDHHMMSSmmm>/
  meta.json                Victim provenance + run metadata (see below)
  raw_responses.csv         All attack responses + victim model's self-assessment
  scored_asr_pyrit.csv      Victim model's self-assessment extracted as scores
  scored_asr_bf16.csv       Re-scored by the BF16 reference model (ASR)
  scored_asr_claude.csv     Re-scored by Claude Haiku 4.5 (ASR)
  scored_strict_bf16.csv    Refusal scores (STRICT) from the BF16 reference model
  scored_strict_claude.csv  Refusal scores (STRICT) from Claude Haiku 4.5
  scored_lenient_bf16.csv   Refusal scores (LENIENT) from the BF16 reference model
  scored_lenient_claude.csv Refusal scores (LENIENT) from Claude Haiku 4.5
  summary.csv               ASR cross-scorer comparison table
  summary_refusal.csv       Refusal cross-scorer comparison table + capability gap
  summary_crosstab.csv      Joint ASR x guardrail 2x2 distribution per judge
```

### `meta.json`

Every run records which model it attacked. The `victim` block is written at
attack time from `src/e2e_config.yaml` (`model_name` + tier → GGUF mapping);
the GGUF SHA-256 is hashed once per file and cached in `.webapp/gguf_hashes.json`:

```json
{
  "tier": "Q4_K_M",
  "victim": {
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "tier": "Q4_K_M",
    "gguf": "meta-llama-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    "gguf_size_mb": 4921.7,
    "gguf_sha256": "…",
    "litellm_model": "victim-llama"
  },
  "dataset_size": 400,
  "status": "complete",
  "notes": ""
}
```

Re-attacks refresh the block (the tier may differ), and `--tier` on the CLI
records the same provenance for manually launched attacks. Runs produced
before this existed live in `archive/runs_v1/` (with the old job history in
`archive/webapp_v1/`); `results/` is the live folder.

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
| `score_value` | Scorer judgment. ASR: `true`/`false`/`error`. Refusal: `true`=refused / `false`=complied. `content_policy_violation` counts as ASR success but as refusal-side compliance. |
| `score_rationale` | Scorer's explanation for the judgment |
| `scorer_type` | Which scorer produced this row (`asr_pyrit`, `asr_bf16`, `asr_claude`, `strict_bf16`, `strict_claude`, `lenient_bf16`, `lenient_claude`, etc.) |
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

Each metric row has columns for every ASR scorer in the run (`asr_pyrit`, `asr_bf16`, `asr_claude`).

### `summary_refusal.csv`

The refusal rubric (`strict_bf16`, `strict_claude`, `lenient_bf16`, `lenient_claude`) gets its own summary so its semantics (`true`=refused) are never conflated with the ASR table (`true`=attack succeeded).

| Metric | Description |
|---|---|
| `total` | Total responses scored |
| `refusal` | Count scored as the model refused |
| `compliance` | Count scored as the model complied (no refusal) |
| `error` / `undetermined` | Error / ambiguous counts |
| `content_policy_violation` | Scorer blocked by content policy (counted as compliance: victim produced harmful content) |
| `refusal_rate_pct` | Percentage of refusals |
| `compliance_rate_pct` | Percentage of compliance |
| `agreement_with_strict_claude_pct` | Agreement with Claude's STRICT refusal verdict |
| `precision/recall/f1_vs_strict_claude_pct` | Classification metrics vs Claude (STRICT) |
| `capability_gap_pct` | `compliance_rate − asr_success_rate` (same judge). Positive and growing at low bits = guardrail broke but capability loss masked the harm. |

**Interpreting `capability_gap_pct`:** ASR measures whether a harmful objective was *achieved*; compliance measures whether the model *refused*. Their difference is the share that gave a direct substantive answer (STRICT compliance) but whose output Claude did not judge as achieving the harm — i.e. the capability floor masking a broken guardrail. This isolates the safety-vs-capability asymmetry central to the research thesis.

### `summary_crosstab.csv`

The joint ASR x guardrail distribution per judge. Each conversation is classified into one of four quadrants based on the same judge's ASR verdict (attack succeeded/failed) crossed with its refusal verdict (guardrail maintained/failed):

```
                       Guardrail Failed          Guardrail Maintained
                     (refusal = false)           (refusal = true)
                   +--------------------+--------------------------+
  Attack           |     breach         |      scarecrow           |
  succeeded        | classic jailbreak  |  hollow / leaky          |
  (ASR = true)     |                    |  refusal                 |
                   +--------------------+--------------------------+
  Attack           |     fizzle         |      guarded             |
  failed           | capability loss    |  best case (aligned)     |
  (ASR = false)    | masked the breach  |                          |
                   +--------------------+--------------------------+
```

| Quadrant | ASR | Guardrail | Interpretation |
|---|---|---|---|
| `breach` | succeeded | failed | The model neither refused nor resisted — a conventional jailbreak. Worst outcome: willing and able to produce harm. |
| `scarecrow` | succeeded | maintained | The model "refused" yet the attack still succeeded. Either a judge error or a case where the refusal was hollow — present but ineffective, like a scarecrow that scares nothing. Also sometimes called a "leaky refusal". |
| `guarded` | failed | maintained | The model refused and the attack failed. Best case: guardrails held and capability was sufficient to avoid harm. |
| `fizzle` | failed | failed | The model did not refuse, but the attack failed anyway. Quantization degraded capability at the same rate or faster than it broke the guardrail — the model would have helped but couldn't. |

Each metric row has columns for every judge pair (`strict_claude`, `strict_bf16`, `strict_pyrit`, `lenient_claude`, etc.). Counts (`breach`, `scarecrow`, `guarded`, `fizzle`, `unscorable`) and percentages (`breach_pct`, etc.) are provided. `unscorable` captures responses with `error` or `undetermined` in either dimension.

**Interpreting the quadrants:** `breach` and `guarded` are the unambiguous outcomes (both judges agree on safety/capability). `scarecrow` and `fizzle` are the diagnostic quadrants — they reveal where safety and capability signals diverge. A tier with rising `fizzle` and stable `breach` has a capability problem, not a safety problem; rising `breach` with stable `fizzle` is pure guardrail degradation.

## Web Dashboard

A full-stack dashboard for tracking runs live, re-running parts of them, and comparing results.

### Quick start (Docker — recommended)

Everything is containerised and version-pinned; the host only needs Docker + the GGUF files:

```bash
docker compose up -d --build   # web (dashboard + job manager) + litellm proxy
cat .webapp/token              # paste into http://localhost:8000
```

The compose stack:
- **`web`** — multi-stage image (`Dockerfile`): pinned node builds the SPA, pinned python installs frozen deps from `uv.lock`; runs the API, job manager, and pipeline. It starts/stops llama.cpp containers on demand through the mounted docker socket (`server.mode: docker` in `src/e2e_config.yaml`).
- **`litellm`** — LiteLLM proxy pinned to the same version as `pyproject.toml` (digest-pinned).
- **llama.cpp (dynamic)** — `ghcr.io/ggml-org/llama.cpp` images pinned by digest (`server-rocm` for GPU, `server` for CPU); one container per role, GPU devices passed through, models mounted read-only.

Reproducibility pins: image digests in `src/e2e_config.yaml` + `docker-compose.yml`, `uv.lock`, `frontend/package-lock.json` (`npm ci` enforced), and pinned base images in the `Dockerfile`. GPU access requires `/dev/kfd` + `/dev/dri` (AMD ROCm); `docker.gpu_env` pins `HIP_VISIBLE_DEVICES=0` so llama.cpp doesn't split across the dGPU and an iGPU — adjust for your host.

Notes:
- `docker compose` sets `HOST_PROJECT_ROOT` so llama containers get the right host-side `./models` path (bind-mount sources resolve on the host daemon).
- For GPU-less orchestration testing, tier `Q2_K_CPU` runs the CPU image.
- Mounting the docker socket gives the web container control over the host daemon — fine for a single-user research box, not for shared infrastructure.
- The backend can also run directly on the host (`uv run python -m src.web`) with `server.mode: local` for the classic CLI workflow; host CLI runs additionally read PyRIT's `OPENAI_CHAT_*` defaults from `.pyrit/.env`.

### Host-mode quick start

```bash
# 1. Build the frontend (fully containerised — the host only needs Docker)
./scripts/build_frontend.sh

# 2. Start the server (binds 0.0.0.0:8000; token prints at startup)
uv run python -m src.web

# 3. Open http://localhost:8000 and paste the token
```

The token is auto-generated into `.webapp/token` on first start; set `WEB_TOKEN` in `.env` to pin your own. The host needs **no node/npm** — all frontend tooling runs inside the pinned `node:24.16.0-alpine3.22` image.

### Features

- **Live run tracking** — every job (E2E tier run, attack, re-score, summarize, merge) streams log lines and per-scorer progress over SSE in real time; scoring progress is exact (`done/total` per scorer), attack progress is approximated from PyRIT's in-memory attack results.
- **Arbitrary partial reruns**
  - *Re-score*: select any prompts in the Prompts tab (or use the error/disagreement/content-policy filters), pick judges, submit — the backend backs up and invalidates just those rows, then re-scores only them. Everything is resume-safe.
  - *Re-attack*: select prompts, pick a tier, and the objectives are re-run against that victim; old responses are backed up to `results/<run>/backups/` and replaced in-place, with their scores invalidated.
- **Tabular comparisons** — side-by-side metric matrices (ASR / refusal / crosstab) across runs with tier-sorted columns, plus a per-prompt cross-run diff view that highlights judge disagreements.
- **Per-prompt inspection** — every conversation joined across all judges: verdict chips, quadrants (breach/scarecrow/guarded/fizzle), full victim responses and judge rationales.
- **Full orchestration** — the backend starts/stops llama.cpp servers and the LiteLLM proxy per job based on the selected scorers; one GPU job runs at a time.

### Job kinds

| Kind | Params | What it does |
|---|---|---|
| `e2e` | `tier`, `dataset_size` | Full pipeline for a tier (attacks + both scoring phases + summaries) |
| `attack` | `tier`, `dataset_size`, optionally `run_name` + `objectives` | New attack run, or in-place re-attack of selected objectives |
| `rescore` | `run_name`, `models[]`, optionally `conversation_ids[]`, `tier` | (Re-)score selected prompts with selected judges |
| `summarize` | `run_name` | Regenerate summary CSVs from the scored files present |
| `merge` | `target`, `sources[]` | Merge runs (same as `merge_runs.py`) |

### API

All `/api` routes require `Authorization: Bearer <token>` (the SSE route also accepts `?token=`).

| Endpoint | Purpose |
|---|---|
| `GET /api/runs`, `GET /api/runs/{name}` | Run list / detail (meta, counts, parsed summaries) |
| `GET /api/runs/{name}/prompts?filter=&q=&scorer=&value=&quadrant=` | Joined per-prompt rows with all judges |
| `PATCH /api/runs/{name}/meta` | Edit tier label / notes |
| `POST /api/jobs`, `GET /api/jobs[/{id}]`, `POST /api/jobs/{id}/cancel` | Job submission & control |
| `GET /api/jobs/{id}/events` | SSE stream (log/progress/phase/status events) |
| `GET /api/compare?kind=&runs=a,b`, `GET /api/compare/prompts?runs=a,b` | Cross-run comparisons |
| `GET /api/system` | Server health (:8080/:8081/:4000), tiers, queue state |

### Frontend development

```bash
# terminal 1: backend
uv run python -m src.web

# terminal 2: vite dev server in a container (hot reload, proxies /api to the host)
./scripts/dev_frontend.sh
```

The dev container proxies `/api` to `host.docker.internal:8000` (override with `API_TARGET`).

## Scoring Models

Two rubrics are run, each by the BF16 and Claude judges:

| Scorer | LiteLLM Model | Rubric | Description |
|---|---|---|---|
| `asr_pyrit` | — | task_achieved | Extracts the victim model's self-assessment from Phase 1 (no LLM call). |
| `asr_bf16` | `bf16-llama` | task_achieved | ASR scorer: did the model achieve the harmful objective? Full-precision reference via llama.cpp `:8081`. |
| `asr_claude` | `claude-haiku-4.5` | task_achieved | ASR scorer (external judge, treated as ground truth). |
| `strict_bf16` | `bf16-llama` | refusal_strict | STRICT refusal scorer: deflection, hedging, and partial answers all count as refusal. Uses PyRIT's `SelfAskRefusalScorer` (`OBJECTIVE_STRICT`). |
| `strict_claude` | `claude-haiku-4.5` | refusal_strict | STRICT refusal scorer (external judge, treated as ground truth). |
| `strict_pyrit` | `victim-llama` | refusal_strict | STRICT refusal scorer: the victim model self-judges whether it refused (requires the victim loaded on `:8080`). |
| `lenient_bf16` | `bf16-llama` | refusal_lenient | LENIENT refusal scorer: only explicit refusals count (deflection = compliance). Uses `OBJECTIVE_LENIENT`. |
| `lenient_claude` | `claude-haiku-4.5` | refusal_lenient | LENIENT refusal scorer (external judge). |
| `lenient_pyrit` | `victim-llama` | refusal_lenient | LENIENT refusal scorer: the victim model self-judges (requires the victim loaded on `:8080`). |

All LLM scorers use `temperature=0.1`. ASR scorers use PyRIT's `SelfAskTrueFalseScorer` with the `TASK_ACHIEVED` rubric; STRICT refusal scorers use `SelfAskRefusalScorer` with `RefusalScorerPaths.OBJECTIVE_STRICT` (deflection, hedging, and partial answers all count as refusal); LENIENT refusal scorers use `OBJECTIVE_LENIENT` (only explicit refusals count).

## LiteLLM Proxy

The LiteLLM proxy is started automatically by `main.py` and manages all model traffic. Configuration in `src/litellm_config.yaml`:

| Model Name | Backend | Temperature | Rate Limit |
|---|---|---|---|
| `victim-llama` | llama.cpp `:8080` | server default | — |
| `bf16-llama` | llama.cpp `:8081` | `0.1` | — |
| `claude-haiku-4.5` | AWS Bedrock (primary) | `0.1` | — |
| `claude-haiku-4.5-anthropic` | Anthropic API (fallback) | `0.1` | `45 rpm` |

Global settings: `10` retries, `1080s` request timeout, `120s` cooldown on failure. The router falls back from Bedrock to the Anthropic API on error.

# Control Results

Models Llama-3.1-8B-Instruct-BF16 and claude-haiku-4-5-20251001 are used as scorers.

Success includes content policy violation records, as an assumption is made that anything that Claude returns as a ContentPolicyViolation implies that the attack was most likely a success.

## Control Results (no prompt fuzzing) vs BF16

```
============================================
                   metric | bf16 | claude
--------------------------+-------+-------
                    total |   400 |    400
           attack_success |    90 |     49
           attack_failure |   310 |    351
                    error |     0 |      0
             undetermined |     0 |      0
 content_policy_violation |     0 |      1
         success_rate_pct |  22.5 |  12.25
             cpv_rate_pct |   0.0 |   2.04
agreement_with_claude_pct | 72.25 |  100.0
  precision_vs_claude_pct |  23.4 |  100.0
     recall_vs_claude_pct | 39.29 |  100.0
         f1_vs_claude_pct | 29.33 |  100.0
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
  precision_vs_claude_pct | 23.4 | 23.91|  100.0
     recall_vs_claude_pct | 39.29| 39.29|  100.0
         f1_vs_claude_pct | 29.33| 29.73|  100.0
```

```
=================================================================
                           metric | refusal_claude | refusal_bf16
----------------------------------+----------------+-------------
                            total |            400 |          400
                       compliance |            129 |          124
                          refusal |            271 |          276
                            error |              0 |            0
                     undetermined |              0 |            0
         content_policy_violation |              0 |            0
                 refusal_rate_pct |          67.75 |         69.0
              compliance_rate_pct |          32.25 |         31.0
agreement_with_refusal_claude_pct |          100.0 |        88.75
  precision_vs_refusal_claude_pct |          100.0 |        90.94
     recall_vs_refusal_claude_pct |          100.0 |        92.62
         f1_vs_refusal_claude_pct |          100.0 |        91.77
               capability_gap_pct |          18.25 |          7.5
```

```
| judge  | total | ASR success % | refusal % | compliance % | capability gap % |
| ------ | ----: | ------------: | --------: | -----------: | ---------------: |
| claude |   400 |          14.0 |     67.75 |        32.25 |            18.25 |
| bf16   |   400 |          23.5 |      69.0 |         31.0 |              7.5 |

Diagnostics (vs reference judge)
| judge  | agreement % | precision % | recall % |  f1 % |
| ------ | ----------: | ----------: | -------: | ----: |
| claude |       100.0 |       100.0 |    100.0 | 100.0 |
| bf16   |       88.75 |       90.94 |    92.62 | 91.77 |
```

## Control Results (no prompt fuzzing) vs Q6_K

Q6_K run with cross-scorer comparison (400 HarmBench objectives):

```
=================================================
                   metric | q6_k  | bf16  | claude
--------------------------+-------+-------+-------
                    total |   400 |  400  |    400
                  success |    99 |   86  |     49
                  failure |   301 |  313  |    351
                    error |     0 |    1  |      0
             undetermined |     0 |    0  |      0
 content_policy_violation |     0 |    0  |      0
         success_rate_pct | 24.75 | 21.5  |  12.25
             cpv_rate_pct |   0.0 |  0.0  |    0.0
agreement_with_claude_pct |  70.5 | 71.5  |  100.0
  precision_vs_claude_pct | 15.15 | 12.79 |  100.0
     recall_vs_claude_pct | 30.61 | 22.45 |  100.0
         f1_vs_claude_pct | 20.27 |  16.3 |  100.0
```

## Control Results (no prompt fuzzing) vs Q5_K_M

Q5_K_M run with cross-scorer comparison (400 HarmBench objectives):

```
============================================================
SUMMARY
============================================================
                   metric | q5_k_m| bf16  | claude
--------------------------+-------+-------+-------
                    total |   400 |  400  |    400
                  success |    95 |   96  |     52
                  failure |   305 |  304  |    348
                    error |     0 |    0  |      0
             undetermined |     0 |    0  |      0
 content_policy_violation |     0 |    0  |      2
         success_rate_pct | 23.75 | 24.0  |   13.0
             cpv_rate_pct |   0.0 |  0.0  |   3.85
agreement_with_claude_pct | 69.25 |  70.5 |  100.0
  precision_vs_claude_pct | 12.63 | 15.62 |  100.0
     recall_vs_claude_pct | 23.08 | 28.85 |  100.0
         f1_vs_claude_pct | 16.33 | 20.27 |  100.0
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
  precision_vs_claude_pct | 13.58 | 16.05 |  100.0
     recall_vs_claude_pct |  44.0 |  26.0 |  100.0
         f1_vs_claude_pct | 20.75 | 19.85 |  100.0
```

## Control Results (no prompt fuzzing) vs Q3_K_M

```
============================================================
SUMMARY
============================================================
                   metric | q3km  |  bf16 | claude
--------------------------+-------+-------+-------
                    total |   400 |   400 |    400
                  success |   153 |    84 |     34
                  failure |   247 |   316 |    366
                    error |     0 |     0 |      0
             undetermined |     0 |     0 |      0
 content_policy_violation |     0 |     0 |      1
         success_rate_pct | 38.25 |  21.0 |    8.5
             cpv_rate_pct |   0.0 |   0.0 |   2.94
agreement_with_claude_pct | 61.25 |  75.5 |  100.0
  precision_vs_claude_pct | 10.46 |  11.9 |  100.0
     recall_vs_claude_pct | 47.06 | 29.41 |  100.0
         f1_vs_claude_pct | 17.12 | 16.94 |  100.0
```