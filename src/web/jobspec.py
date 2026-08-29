"""Job validation: normalise and check job params before queueing.

Called by the API on submit; raises ``ValueError`` with a user-facing
message on bad input.  Pure validation — no side effects.
"""

from src import tiers
from src.run_meta import read_meta
from src.scorers import SCORER_SPECS, VALID_SCORERS
from src.web import runs


def validate_job(kind: str, params: dict) -> tuple[dict, str | None]:
    """Normalise and validate *params*; returns ``(params, run_name)``.

    Raises ``ValueError`` with a user-facing message on bad input.
    """
    if kind == "e2e":
        tier = str(params.get("tier", "")).upper()
        if not tier:
            raise ValueError("tier is required")
        config = tiers.load_config()
        tiers.resolve_gguf(tier, config)  # raises if unknown tier / missing GGUF
        size = int(params.get("dataset_size", 400))
        if size < 1:
            raise ValueError("dataset_size must be >= 1")
        return {"tier": tier, "dataset_size": size}, None

    if kind == "attack":
        tier = str(params.get("tier", "")).upper()
        if not tier:
            raise ValueError("tier is required")
        config = tiers.load_config()
        tiers.resolve_gguf(tier, config)
        size = int(params.get("dataset_size", 400))
        if size < 1:
            raise ValueError("dataset_size must be >= 1")
        run_name = params.get("run_name")
        objectives = params.get("objectives") or []
        if run_name is not None:
            if not runs.run_exists(run_name):
                raise ValueError(f"run not found: {run_name}")
            if not objectives:
                raise ValueError("re-attack requires a non-empty objectives list")
        return {
            "tier": tier, "dataset_size": size,
            "run_name": run_name, "objectives": list(objectives),
        }, run_name

    if kind == "rescore":
        run_name = str(params.get("run_name", ""))
        if not runs.run_exists(run_name):
            raise ValueError(f"run not found: {run_name}")
        models = params.get("models") or list(VALID_SCORERS)
        invalid = [m for m in models if m not in VALID_SCORERS]
        if invalid:
            raise ValueError(f"unknown scorers: {', '.join(invalid)}")
        conversation_ids = params.get("conversation_ids") or None
        if conversation_ids is not None and not conversation_ids:
            raise ValueError("conversation_ids must be non-empty when provided")
        tier = params.get("tier")
        if tier:
            tier = str(tier).upper()
            config = tiers.load_config()
            tiers.resolve_gguf(tier, config)
        else:
            needs_victim = any(SCORER_SPECS[m]["model"] == "victim-llama" for m in models if m in SCORER_SPECS)
            meta = read_meta(runs.run_dir(run_name))
            meta_tier = meta.get("tier") or (meta.get("victim") or {}).get("tier")
            if needs_victim and not meta_tier:
                raise ValueError("run has no tier in meta.json and *_pyrit scorers need the "
                                 "victim model — pass an explicit tier")
        return {
            "run_name": run_name, "models": list(models),
            "conversation_ids": list(conversation_ids) if conversation_ids else None,
            "tier": tier,
        }, run_name

    if kind == "summarize":
        run_name = str(params.get("run_name", ""))
        if not runs.run_exists(run_name):
            raise ValueError(f"run not found: {run_name}")
        return {"run_name": run_name}, run_name

    if kind == "merge":
        target = str(params.get("target", ""))
        sources = params.get("sources") or []
        if not runs.run_exists(target):
            raise ValueError(f"target run not found: {target}")
        for s in sources:
            if not runs.run_exists(s):
                raise ValueError(f"source run not found: {s}")
        if target in sources:
            raise ValueError("target cannot also be a source")
        if not sources:
            raise ValueError("sources must be non-empty")
        return {"target": target, "sources": list(sources)}, target

    raise ValueError(f"unknown job kind: {kind}")
