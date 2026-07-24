import subprocess
import sys
import time
from pathlib import Path

from src.http_health import is_healthy

LITELLM_PORT = 4000
LITELLM_CONFIG = str(Path(__file__).parent / "litellm_config.yaml")
PROXY_STARTUP_TIMEOUT = 60


def start_litellm_proxy(port: int = LITELLM_PORT, config_path: str = LITELLM_CONFIG, timeout: int = PROXY_STARTUP_TIMEOUT) -> subprocess.Popen | None:
    if is_healthy(port):
        print("LiteLLM proxy already running.")
        return None

    litellm_bin = str(Path(sys.executable).parent / "litellm")
    proc = subprocess.Popen(
        [litellm_bin, "--config", config_path, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    print(f"Starting LiteLLM proxy on port {port} ...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if is_healthy(port):
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
