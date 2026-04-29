import subprocess
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    import urllib.request
    httpx = None

LITELLM_PORT = 4000
LITELLM_CONFIG = str(Path(__file__).parent / "litellm_config.yaml")
PROXY_STARTUP_TIMEOUT = 60


def _is_proxy_healthy(port: int) -> bool:
    try:
        if httpx is not None:
            resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
            return resp.status_code == 200
        else:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            return True
    except Exception:
        return False


def start_litellm_proxy(port: int = LITELLM_PORT, config_path: str = LITELLM_CONFIG, timeout: int = PROXY_STARTUP_TIMEOUT) -> subprocess.Popen | None:
    if _is_proxy_healthy(port):
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
            if _is_proxy_healthy(port):
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
