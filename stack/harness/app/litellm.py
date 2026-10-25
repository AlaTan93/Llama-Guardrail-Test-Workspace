"""Single LiteLLM client for the harness.

Every consumer of the proxy's management API goes through here — the
``/api/models`` route, the run worker's routing snapshots, and the health
check — so when LiteLLM's management API drifts again (it will), this is the
only file to fix.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.config import settings


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.litellm_api_key}"}


def _alias_of(row: dict) -> str | None:
    """model_name lives at the row top level; model_info holds id/metadata."""
    return row.get("model_name") or row.get("model_info", {}).get("model_name")


async def model_info_rows() -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{settings.litellm_admin_url}/model/info", headers=_headers())
        resp.raise_for_status()
        return resp.json().get("data", [])


async def aliases() -> list[str]:
    rows = await model_info_rows()
    return sorted({name for row in rows if (name := _alias_of(row))})


async def routing_snapshot(aliases: list[str]) -> dict:
    """Record the live routing for the given aliases so historical results
    stay interpretable after aliases are re-pointed."""
    snapshot: dict = {"captured_at": datetime.now(UTC).isoformat(), "models": {}}
    try:
        rows = await model_info_rows()
        wanted = set(aliases)
        for row in rows:
            name = _alias_of(row)
            if name in wanted:
                params = row.get("litellm_params", {})
                snapshot["models"][name] = {k: params.get(k) for k in ("model", "api_base")}
    except Exception as exc:  # noqa: BLE001 — snapshot is best-effort provenance
        snapshot["warning"] = f"routing snapshot failed: {exc!r}"
    return snapshot


async def reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.litellm_admin_url}/health/liveliness")
            return resp.status_code < 500
    except Exception:  # noqa: BLE001
        return False
