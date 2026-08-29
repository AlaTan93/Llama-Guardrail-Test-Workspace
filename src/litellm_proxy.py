import os
import subprocess
import sys
import time
from pathlib import Path

from src.config import LITELLM_PORT
from src.http_health import is_healthy

LITELLM_CONFIG = str(Path(__file__).parent / "litellm_config.yaml")
PROXY_STARTUP_TIMEOUT = 60

# LiteLLM's `/health` performs live model checks (hangs when llama servers are
# down); these endpoints are cheap liveness probes.
HEALTH_ENDPOINTS = ("/health/liveliness", "/v1/models")

# Defaults for the env-templated api_base entries in litellm_config.yaml.
# Compose overrides these with container hostnames.
_API_BASE_DEFAULTS = {
    "VICTIM_API_BASE": "http://127.0.0.1:8080/v1",
    "BF16_API_BASE": "http://127.0.0.1:8081/v1",
}


def _wait_healthy(port: int, host: str, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if is_healthy(port, HEALTH_ENDPOINTS, host=host):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_litellm_proxy(port: int = LITELLM_PORT, config_path: str = LITELLM_CONFIG, timeout: int = PROXY_STARTUP_TIMEOUT) -> subprocess.Popen | None:
    host = os.environ.get("LITELLM_HOST", "127.0.0.1")

    if _wait_healthy(port, host, 5):
        print("LiteLLM proxy already running.")
        return None

    external = host not in ("127.0.0.1", "localhost", "")
    if external:
        # Managed externally (docker compose): never spawn, just wait.
        if _wait_healthy(port, host, timeout):
            print(f"External LiteLLM proxy at {host}:{port} is ready.")
            return None
        raise RuntimeError(f"External LiteLLM proxy at {host}:{port} did not become healthy "
                           f"within {timeout}s — check the compose service.")

    for key, default in _API_BASE_DEFAULTS.items():
        os.environ.setdefault(key, default)

    litellm_bin = str(Path(sys.executable).parent / "litellm")
    proc = subprocess.Popen(
        [litellm_bin, "--config", config_path, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    print(f"Starting LiteLLM proxy on {host}:{port} ...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if is_healthy(port, HEALTH_ENDPOINTS, host=host):
                print("LiteLLM proxy is ready.")
                return proc
        except Exception:
            pass
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode() if proc.stdout else ""
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"LiteLLM proxy exited early.\nstdout: {stdout}\nstderr: {stderr}")
        time.sleep(1)

    proc.terminate()
    raise RuntimeError(f"LiteLLM proxy did not become healthy within {timeout}s")
