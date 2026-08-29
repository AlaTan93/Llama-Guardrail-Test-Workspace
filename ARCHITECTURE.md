# Architecture

How the quantization red-teaming stack fits together — layers, data flow,
jobs, and the container topology.  Cross-linked from module docstrings;
see `README.md` for usage.

## Layer diagram

```
┌────────────────────────────────────────────────────────────────────┐
│ ENTRY POINTS                                                       │
│   main.py (CLI)              src/web/ (dashboard API + SPA)        │
│        │                          │                                │
│        │                   src/web/jobspec.py  (validation)        │
│        │                   src/web/job_manager.py (queue + SSE)    │
│        │                          │                                │
│        │                   src/web/runners.py  (JobProgress,       │
│        │                                    job execution)         │
├────────┼──────────────────────────┼────────────────────────────────┤
│ PIPELINE (kind-agnostic: CLI and web both call these)              │
│   src/e2e.py        two-phase orchestration per tier               │
│   src/redteam.py    PyRIT attacks (new run / in-place re-attack)   │
│   src/scoring.py    judge loops, retries, invalidation, resume     │
│   src/summaries.py  summary.csv / refusal / crosstab generation    │
├────────────────────────────────────────────────────────────────────┤
│ REGISTRIES & CONTRACTS                                             │
│   src/scorers.py    judge × rubric registry (single source)        │
│   src/tiers.py      tier → GGUF / docker-image mapping             │
│   src/progress.py   ProgressReporter protocol (no-op default)      │
│   src/config.py     paths, service hosts, CSV schemas              │
├────────────────────────────────────────────────────────────────────┤
│ INFRASTRUCTURE                                                      │
│   src/servers.py        ServerStack: llama + LiteLLM lifecycle     │
│   src/llama_server.py   launch primitives (local binary | docker)  │
│   src/litellm_proxy.py  proxy bring-up (spawn or external)         │
│   src/judges.py         PyRIT scorer construction + JSON sanitize  │
├────────────────────────────────────────────────────────────────────┤
│ ARTIFACTS (source of truth — everything else is derived)           │
│   results/run_*/raw_responses.csv, scored_<scorer>.csv,            │
│   summary*.csv, meta.json, backups/                                │
└────────────────────────────────────────────────────────────────────┘
```

Support modules: `runs_io.py` (run persistence from the attack phase),
`run_meta.py` (`meta.json` read/merge), `victim_meta.py` (victim provenance
+ cached GGUF SHA-256), `metrics.py` (counts/agreement/F1/crosstab from
scored CSVs), `csv_io.py` (CSV helpers + row surgery), `http_health.py`,
`json_sanitize.py`, `patches.py` (PyRIT monkey-patches — imported first).

Web-only: `web/app.py` (FastAPI factory + SPA hosting), `web/auth.py`
(bearer token; `?token=` for EventSource), `web/settings.py` (state paths,
token), `web/runs.py` (run directory access), `web/views.py` (per-prompt
joins, filters, comparisons).

## Life of a run (data flow)

1. **Attack** (`redteam.run_attacks`) — PyRIT sends HarmBench objectives at
   the victim through LiteLLM; the victim self-judges each response
   (`pyrit_outcome`).  `runs_io` writes `raw_responses.csv` + `meta.json`
   (victim provenance: model, tier, GGUF size + SHA-256, LiteLLM alias).
   Re-attacks instead back up, drop, and replace the affected rows and
   invalidate their `conversation_id`s from every `scored_*.csv`.
2. **Scoring** (`scoring.score_responses` per judge) — each judge in
   `scorers.py` re-scores every response, appending one row at a time to
   `scored_<scorer>.csv` (resumable: already-present `conversation_id`s are
   skipped; subset re-scoring deletes selected rows first — always backed up).
3. **Summaries** (`summaries.py` + `metrics.py`) — derived, cheap to
   regenerate: ASR table, refusal table (with capability gap), ASR ×
   guardrail crosstab (breach / scarecrow / guarded / fizzle).

Invariants:
- **CSVs are the source of truth.** `meta.json` is metadata; summaries are
  derived; `.webapp/` is UI state only.
- **Scores are keyed by `conversation_id`**; joining raw ↔ scored is by
  `conversation_id`, cross-run comparison by objective text.
- **One GPU job at a time** — the job manager runs jobs serially.

## Job lifecycle (web)

`POST /api/jobs` → `jobspec.validate_job` (pure checks) → queue →
`runners.run_job` (async task) → SSE events streamed to
`/api/jobs/{id}/events` (`log` / `progress` / `phase` / `status`).  Runners
wrap pipeline calls in `ServerStack` context managers and a `JobProgress`
adapter that turns `ProgressReporter` calls into SSE events.  Logs persist
under `.webapp/logs/`; the registry `.webapp/jobs.json` survives restarts.

## Container topology (docker compose)

```
redteam network
├── redteam-web-1      image: built Dockerfile (SPA + python + docker CLI)
│     ├── serves :8000 (API + SPA)
│     ├── runs the pipeline (PyRIT → LiteLLM over the network)
│     └── starts/stops llama.cpp containers via the mounted docker socket
├── redteam-litellm-1  image: litellm/litellm (pinned)  — :4000
│     └── routes: victim-llama / bf16-llama / claude-haiku-4.5
├── redteam-victim     image: ggml-org/llama.cpp server-rocm (pinned, GPU)
└── redteam-bf16       image: same — created/removed per job phase
```

- Bind-mount sources for llama containers resolve on the **host** daemon, so
  the web backend translates `./models` via `HOST_PROJECT_ROOT` (compose sets
  it from `${PWD}`; a mountinfo probe is the fallback).
- `gpu_env: HIP_VISIBLE_DEVICES=0` pins llama.cpp to the dGPU (it would
  otherwise split across dGPU + iGPU and crash).
- Hosts are env-templated: `VICTIM_HOST` / `BF16_HOST` / `LITELLM_HOST`
  (default `127.0.0.1` keeps host-mode CLI runs working unchanged);
  LiteLLM's `api_base` entries come from `VICTIM_API_BASE` / `BF16_API_BASE`.

## Frontend (`frontend/`, built in a pinned node container)

React + TS + Vite + Tailwind; TanStack Query (polling/SSE refresh) and
Table.  Pages: `Dashboard` (run list), `RunDetail` (overview summaries /
`PromptsTable` / meta), `Jobs` (`JobList` + live `JobConsole`),
`NewRun` (wizard), `Compare` (metric matrices + per-prompt diff).  Shared:
`components/ui.tsx` (badges/chips/tables), `hooks/useSubmitJob.ts`.
Auth: token stored in localStorage, sent as a bearer header (`?token=` for
EventSource).
