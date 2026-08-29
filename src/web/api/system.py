"""System status: server health, tiers, queue."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request

from src import tiers
from src.config import BF16_HOST, LITELLM_HOST, VICTIM_HOST
from src.http_health import is_healthy
from src.litellm_proxy import HEALTH_ENDPOINTS as LITELLM_HEALTH
from src.scorers import VALID_SCORERS
from src.web.auth import require_token

router = APIRouter(prefix="/system", dependencies=[Depends(require_token)], tags=["system"])


@router.get("")
def system(request: Request) -> dict:
    config = tiers.load_config()
    models_dir = Path(config.get("models_dir", "./models"))

    tier_list = []
    for tier in sorted(config.get("tiers", {})):
        gguf_file, image = tiers.tier_entry(config, tier)
        if not gguf_file:
            continue
        tier_list.append({
            "tier": tier,
            "gguf": gguf_file,
            "available": (models_dir / gguf_file).exists(),
            "image": image or "default",
        })

    manager = request.app.state.jobs
    current = manager.current()
    queued = sum(1 for j in manager.jobs.values() if j.status == "queued")

    return {
        "servers": {
            "victim_8080": is_healthy(8080, ("/health", "/v1/models"), host=VICTIM_HOST),
            "bf16_8081": is_healthy(8081, ("/health", "/v1/models"), host=BF16_HOST),
            "litellm_4000": is_healthy(4000, LITELLM_HEALTH, host=LITELLM_HOST),
        },
        "tiers": tier_list,
        "scorers": VALID_SCORERS,
        "queue": {"current": current.record() if current else None, "queued": queued},
    }
