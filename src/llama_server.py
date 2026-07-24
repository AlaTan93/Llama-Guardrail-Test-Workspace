"""llama.cpp server lifecycle management.

Starts and stops ``llama-server`` subprocesses on configurable ports, waiting
for health before returning and ensuring GPU memory is released on shutdown.
"""

import subprocess
import time

from src.http_health import is_healthy


def _build_command(gguf_path: str, port: int, config: dict) -> list[str]:
    srv = config["server"]
    binary = srv["binary"]
    host = srv.get("host", "127.0.0.1")
    ngl = srv.get("ngl", 99)
    extra = list(srv.get("extra_args", []))
    return [binary, "-m", gguf_path, "--host", host, "--port", str(port), "-ngl", str(ngl)] + extra


def start_server(gguf_path: str, port: int, config: dict) -> subprocess.Popen:
    """Start ``llama-server`` with *gguf_path* on *port* and block until healthy."""
    cmd = _build_command(gguf_path, port, config)
    timeouts = config.get("timeouts", {})
    startup_timeout = timeouts.get("startup", 120)

    print(f"Starting llama-server on :{port}")
    print(f"  cmd: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        if is_healthy(port, ("/health", "/v1/models")):
            print(f"llama-server on :{port} is ready.")
            return proc
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(
                f"llama-server on :{port} exited early (code {proc.returncode}).\n"
                f"stdout: {stdout[-2000:]}\nstderr: {stderr[-2000:]}"
            )
        time.sleep(2)

    proc.kill()
    raise RuntimeError(f"llama-server on :{port} did not become healthy within {startup_timeout}s")


def stop_server(proc: subprocess.Popen | None, config: dict) -> None:
    """Terminate *proc* (SIGTERM -> SIGKILL) and wait for GPU memory release."""
    if proc is None or proc.poll() is not None:
        return

    timeouts = config.get("timeouts", {})
    shutdown_timeout = timeouts.get("shutdown", 30)
    gpu_release_delay = timeouts.get("gpu_release_delay", 5)

    print("Stopping llama-server ...")
    proc.terminate()
    try:
        proc.wait(timeout=shutdown_timeout)
        print("llama-server stopped.")
    except subprocess.TimeoutExpired:
        print(f"  did not exit within {shutdown_timeout}s, sending SIGKILL ...")
        proc.kill()
        proc.wait()
        print("llama-server killed.")

    if gpu_release_delay > 0:
        print(f"  waiting {gpu_release_delay}s for GPU memory release ...")
        time.sleep(gpu_release_delay)
