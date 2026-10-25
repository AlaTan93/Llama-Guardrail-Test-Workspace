"""Register the four LiteLLM aliases (DB-backed, no restart needed).

Stdlib only (urllib) so it runs on any host python — no httpx/venv needed.

Usage (defaults read from stack/.env):
    python scripts/bootstrap_models.py --list
    python scripts/bootstrap_models.py --all
    python scripts/bootstrap_models.py --alias target-model --api-base http://llama:8080/v1 --model openai/foo

Idempotent: every existing row for an alias is deleted first (LiteLLM's model
registry can serve stale reads after writes), then one fresh row is added.

The victim's judge-self alias intentionally routes to the same endpoint as
target-model but is a separate row, so it can carry different sampling
defaults later without touching the target.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

try:  # optional .env support when run outside compose
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

ADMIN_URL = os.environ.get("LITELLM_ADMIN_URL", "http://localhost:4010")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
API_KEY = os.environ.get("LITELLM_API_KEY", MASTER_KEY)

BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "bedrock/anthropic.claude-haiku-4-5-20251001")

VICTIM_API_BASE = os.environ.get("VICTIM_API_BASE", "http://host.docker.internal:8080/v1")
BF16_API_BASE = os.environ.get("BF16_API_BASE", "http://host.docker.internal:8081/v1")
VICTIM_MODEL_ID = os.environ.get("VICTIM_MODEL_ID", "meta-llama-3.1-8b-instruct")
BF16_MODEL_ID = os.environ.get("BF16_MODEL_ID", "meta-llama-3.1-8b-instruct-bf16")

# Alias -> litellm_params. llama.cpp speaks the OpenAI wire format, so routes
# use the openai/ provider with api_base pointing at the llama-server.
DEFAULT_MODELS: dict[str, dict] = {
    "target-model": {
        "model": f"openai/{VICTIM_MODEL_ID}",
        "api_base": VICTIM_API_BASE,
        "api_key": "not-needed",
    },
    "judge-self": {
        "model": f"openai/{VICTIM_MODEL_ID}",
        "api_base": VICTIM_API_BASE,
        "api_key": "not-needed",
        "temperature": 0.0,
    },
    "judge-bf16": {
        "model": f"openai/{BF16_MODEL_ID}",
        "api_base": BF16_API_BASE,
        "api_key": "not-needed",
        "temperature": 0.0,
    },
    "judge-claude": {
        "model": BEDROCK_MODEL,
        "temperature": 0.0,
    },
}


def _headers() -> dict[str, str]:
    if not API_KEY:
        raise SystemExit("LITELLM_MASTER_KEY (or LITELLM_API_KEY) not set; copy .env.example to .env first.")
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{ADMIN_URL}{path}", data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def _alias_of(row: dict) -> str | None:
    """model_name lives at the row top level; model_info holds id/metadata."""
    return row.get("model_name") or row.get("model_info", {}).get("model_name")


def list_models() -> None:
    info = _request("GET", "/model/info")
    rows = info.get("data", []) if isinstance(info, dict) else []
    if not rows:
        print("No models registered yet.")
        return
    print(f"{'alias':<16} {'model':<58} api_base")
    for row in rows:
        name = _alias_of(row) or "?"
        params = row.get("litellm_params", {})
        print(f"{name:<16} {str(params.get('model', '?')):<58} {params.get('api_base', '-')}")


def upsert_model(alias: str, params: dict) -> None:
    info = _request("GET", "/model/info")
    rows = info.get("data", []) if isinstance(info, dict) else []

    for row in rows:
        if _alias_of(row) == alias:
            model_id = row.get("model_info", {}).get("id")
            if model_id:
                _request("POST", "/model/delete", {"id": model_id})

    _request("POST", "/model/new", {"model_name": alias, "litellm_params": params})
    print(f"set      {alias}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list registered aliases")
    parser.add_argument("--all", action="store_true", help="register all default aliases")
    parser.add_argument("--alias", help="register one alias with explicit values")
    parser.add_argument("--model", help="litellm model string (e.g. openai/foo, bedrock/...)")
    parser.add_argument("--api-base", help="api_base for openai-compatible backends")
    args = parser.parse_args()

    if args.list or not (args.all or args.alias):
        list_models()
        return
    if args.all:
        for alias, params in DEFAULT_MODELS.items():
            upsert_model(alias, params)
        list_models()
        return
    if args.alias:
        if not args.model:
            raise SystemExit("--alias requires --model")
        params: dict = {"model": args.model}
        if args.api_base:
            params["api_base"] = args.api_base
            params["api_key"] = "not-needed"
        upsert_model(args.alias, params)
        list_models()


if __name__ == "__main__":
    main()
