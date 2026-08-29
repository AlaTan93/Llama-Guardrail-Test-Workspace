"""Shared HTTP health-check (httpx is a hard transitive dep via pyrit)."""

import httpx


def is_healthy(port: int, endpoints: tuple[str, ...] = ("/health",), host: str = "127.0.0.1") -> bool:
    """Return ``True`` if any endpoint on ``{host}:{port}`` responds 200.

    *endpoints* are path suffixes (e.g. ``"/health"``, ``"/v1/models"``) that
    will be tried in order until one succeeds.
    """
    for ep in endpoints:
        url = f"http://{host}:{port}{ep}"
        try:
            resp = httpx.get(url, timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            continue
    return False
