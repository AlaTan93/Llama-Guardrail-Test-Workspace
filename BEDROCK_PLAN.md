# Plan: Switch Claude to AWS Bedrock + re-score all tiers

Goal: serve Claude Haiku 4.5 (the ground-truth judge) via **Amazon Bedrock** so AWS
credits absorb the scoring cost, and re-score every tier's Claude-dependent scores
through the single Bedrock backend so all numbers are internally consistent.

The exact model in use (`claude-haiku-4-5-20251001`) is available on Bedrock as the
same dated snapshot, so behavior is equivalent (same weights; at `temperature=0.1`
only sampling noise differs on borderline calls). Because all Claude traffic already
routes through LiteLLM under the `model_name` `claude-haiku-4.5`, **no application
code changes** — only `litellm_config.yaml`, a dependency, env vars, and one regex.

Decisions locked in:
- **Switch outright** to Bedrock (accept the small sampling-noise confound).
- **Re-score everything via one backend** so the capability-gap metric (refusal_claude
  vs asr_claude) does not span two backends.

---

## Part A — One-time setup

| # | Action | Where |
|---|---|---|
| A1 | Enable Claude Haiku 4.5 model access in Bedrock (pick a region); create IAM keys (or a Bedrock API key via `AWS_BEARER_TOKEN_BEDROCK`) | AWS console |
| A2 | `uv add boto3` (LiteLLM needs boto3 for Bedrock) | `pyproject.toml` |
| A3 | Swap the `claude-haiku-4.5` entry to Bedrock; keep `model_name` unchanged; comment out old Anthropic entry for rollback | `src/litellm_config.yaml` |
| A4 | Replace `ANTHROPIC_API_KEY` with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION_NAME` | `.env.template` (fill `.env`) |
| A5 | Smoke test: one completion through the proxy to confirm auth + model access + region | runtime |

### A3 config diff (`src/litellm_config.yaml`)

`model_name` stays `claude-haiku-4.5`, so `SCORER_SPECS` / `scoring.py` / `main.py`
are untouched:

```yaml
  # --- old (comment out for rollback) ---
  # - model_name: claude-haiku-4.5
  #   litellm_params:
  #     model: anthropic/claude-haiku-4-5-20251001
  #     api_key: os.environ/ANTHROPIC_API_KEY
  #     temperature: 0.1
  #     rpm: 45

  - model_name: claude-haiku-4.5
    litellm_params:
      model: bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0   # us. = cross-region inference
      aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
      aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
      aws_region_name: os.environ/AWS_REGION_NAME
      temperature: 0.1
```

The `us.` prefix enables cross-region inference (better availability/throughput).

### A4 `.env.template`

```
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION_NAME=
```

(`.env` is already gitignored.)

### A5 smoke test (after `litellm` proxy is up)

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4.5","messages":[{"role":"user","content":"ping"}],"max_tokens":16}'
```

Expect a normal completion. Errors here point to: model-access not enabled, wrong
region, or bad credentials.

---

## Part B — Harden content-policy detection for Bedrock

Bedrock surfaces input/output content filtering differently (and often more strictly)
than the Anthropic API. The current `_CONTENT_POLICY_RE` (`src/scoring.py:84`) matches
Anthropic-style strings:

```python
_CONTENT_POLICY_RE = re.compile(
    r"content_filter|content.policy|policy.violation|moderation.blocked"
    r"|flagged as potentially violating|blocked by content filter",
    re.IGNORECASE,
)
```

A Bedrock content block that doesn't match would be miscounted as a generic `error`
instead of `content_policy_violation`, skewing ASR, refusal, and the capability gap.

- **B1:** Broaden the regex defensively (add `content filter`, `guardrail`, `filtered`).
- **B2 (empirical, needs live Bedrock):** Run a few known-harmful scorer prompts through
  Bedrock, capture the exact error string, then lock the regex. This is the one piece
  that cannot be finalized without the live service.

Suggested broadened regex (tune after B2):

```python
_CONTENT_POLICY_RE = re.compile(
    r"content_filter|content filter|content.policy|policy.violation"
    r"|moderation.blocked|flagged as potentially violating|blocked by content filter"
    r"|guardrail|filtered",
    re.IGNORECASE,
)
```

---

## Part C — Re-score all tiers (the consistency step)

> **Critical:** scoring is resumable — it *skips* already-scored `conversation_id`s.
> Each run's stale `scored_claude.csv` (Anthropic-sourced) **must be deleted first**,
> or it is silently skipped and never re-scored via Bedrock.

Refusal scoring splits by where the judge runs:
- **Claude side (Bedrock, no GPU needed):** ASR `claude` + `refusal_claude`
- **BF16 side (local GPU, BF16 model on `:8081`):** `refusal_bf16` is *new* for every
  tier; existing `scored_bf16.csv` is local and unaffected by the backend switch
  (keep as-is, or refresh optionally).

Per tier (`<tier>` = run dir name):

```bash
# C1 — Claude via Bedrock (no local servers required)
rm results/run_<tier>/scored_claude.csv
python main.py --skip-attack --run-dir results/run_<tier> --models claude,refusal_claude

# C2 — BF16 refusal (load BF16 model on :8081 first)
python main.py --skip-attack --run-dir results/run_<tier> --models refusal_bf16

# C3 — regenerate full 5-scorer summaries (no model calls; all files already present)
python main.py --skip-attack --run-dir results/run_<tier> --models pyrit,bf16,claude,refusal_bf16,refusal_claude
```

After all tiers are done, rebuild any cross-tier merged run with:

```bash
python merge_runs.py --target results/run_<merged> --sources <tier run dirs>
```

---

## Part D — Docs

Note the Bedrock backend (and that all numbers are now single-backend consistent) in
`README.md` and `PROJECT_STATUS.md`.

---

## Cost

~6 tiers x 400 objectives x 2 (ASR `claude` + `refusal_claude`) = ~4800 Bedrock Claude
calls. At Haiku 4.5 per-token pricing with short scorer prompts, roughly **$5–10 total**
— well inside AWS credits. BF16 / `refusal_bf16` are local (free).

---

## Inputs needed from the user

1. **AWS region** Claude was enabled in (drives A3/A4). `us-east-1` and `us-west-2` both
   carry Haiku 4.5.
2. **Tier -> run-dir mapping** (only needed for the final comparison tables; the
   rescoring itself is identical per dir). No tier label is currently stored in runs.

## Optional nice-to-have

Write a small `meta.json` (tier label + judge backend) into each run dir so runs are
self-describing. Out of scope unless requested.

## Execution order

A (setup) -> B2 (regex tune, once Bedrock live) -> C (re-score tiers) -> D (docs).
