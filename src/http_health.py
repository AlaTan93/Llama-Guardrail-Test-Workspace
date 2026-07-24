"""Shared HTTP health-check with graceful httpx / urllib fallback."""

try:
    import httpx
except ImportError:
    import urllib.request
    httpx = None


def is_healthy(port: int, endpoints: tuple[str, ...] = ("/health",)) -> bool:
    """Return ``True`` if any endpoint on ``127.0.0.1:{port}`` responds 200.

    *endpoints* are path suffixes (e.g. ``"/health"``, ``"/v1/models"``) that
    will be tried in order until one succeeds.
    """
    for ep in endpoints:
        url = f"http://127.0.0.1:{port}{ep}"
        try:
            if httpx is not None:
                resp = httpx.get(url, timeout=2)
                if resp.status_code == 200:
                    return True
            else:
                urllib.request.urlopen(url, timeout=2)
                return True
        except Exception:
            continue
    return False
