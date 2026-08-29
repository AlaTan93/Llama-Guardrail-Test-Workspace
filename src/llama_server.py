"""llama.cpp server lifecycle management (local subprocess or Docker container).

``server.mode`` in ``e2e_config.yaml`` selects the backend:

- ``local``:  spawn the host binary (classic CLI workflow)
- ``docker``: run a pinned llama.cpp container on the shared compose network,
  with the models directory mounted read-only and GPU devices passed through
  when enabled.  Containers are named ``redteam-<role>`` so LiteLLM (and the
  web backend) can reach them by hostname.

Both modes return a :class:`ServerHandle` that :func:`stop_server` tears down.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from src.http_health import is_healthy

ROLE_HOST_ENV = {"victim": "VICTIM_HOST", "bf16": "BF16_HOST"}


@dataclass
class ServerHandle:
    kind: str                      # "local" | "docker"
    name: str                      # container name (docker); "" for local
    proc: subprocess.Popen | None  # local subprocess


def role_host(role: str) -> str:
    """Hostname through which *role* is reachable from this process."""
    return os.environ.get(ROLE_HOST_ENV.get(role, ""), "127.0.0.1")


def _bind_source(path: Path) -> str | None:
    """Host-side source of the bind mount mounted at *path* (mountinfo)."""
    try:
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            fields = line.split()
            if len(fields) > 4 and fields[4] == str(path):
                tail = line.split(" - ", 1)
                if len(tail) == 2:
                    parts = tail[1].split()
                    if len(parts) >= 2 and parts[0] != "overlay" and parts[1].startswith("/"):
                        return parts[1]
    except OSError:
        pass
    return None


def host_models_dir(config: dict) -> str:
    """Models dir as seen by the docker daemon (host filesystem).

    ``docker run -v`` sources are resolved by the daemon on the host, so when
    this code runs inside a container we must translate the mounted path.
    ``HOST_PROJECT_ROOT`` (set by compose) wins; a bind-mount mountinfo probe
    is the fallback.
    """
    models_dir = Path(config.get("models_dir", "./models"))
    host_root = os.environ.get("HOST_PROJECT_ROOT")
    if host_root:
        cand = Path(host_root) / models_dir if not models_dir.is_absolute() else models_dir
        return str(cand)
    resolved = models_dir.resolve()
    src = _bind_source(resolved)
    if src:
        return src
    if not Path("/.dockerenv").exists():
        return str(resolved)
    raise RuntimeError(
        "cannot determine the host path of the models directory from inside a "
        "container — set HOST_PROJECT_ROOT to the repo path on the host"
    )


# ── Docker mode ────────────────────────────────────────────────────

def select_image(docker_cfg: dict, image_override: str | None) -> tuple[str, bool]:
    """(image, use_gpu) honouring the per-tier override and the gpu flag."""
    gpu = bool(docker_cfg.get("gpu", True)) and image_override != "cpu"
    if image_override == "gpu":
        gpu = True
    image = docker_cfg["image_gpu"] if gpu else docker_cfg["image_cpu"]
    return image, gpu


def build_docker_run_args(
    gguf_path: str,
    port: int,
    config: dict,
    role: str,
    image_override: str | None = None,
) -> list[str]:
    """Pure builder: the ``docker run`` argv for a llama.cpp server container."""
    srv = config["server"]
    dock = srv.get("docker", {})
    image, gpu = select_image(dock, image_override)

    mount = dock.get("models_dir_mount", "/models")
    gguf_in_container = f"{mount}/{Path(gguf_path).name}"

    args = [
        "docker", "run", "-d",
        "--name", f"redteam-{role}",
        "--network", dock.get("network", "redteam"),
        "-v", f"{host_models_dir(config)}:{mount}:ro",
    ]
    if gpu:
        args += [
            "--device", "/dev/kfd",
            "--device", "/dev/dri",
            "--group-add", "video",
            "--group-add", "render",
        ]
        for k, v in (dock.get("gpu_env") or {}).items():
            args += ["--env", f"{k}={v}"]
    if dock.get("publish", False):
        args += ["-p", f"{port}:{port}"]

    args.append(image)
    args += [
        "-m", gguf_in_container,
        "--host", "0.0.0.0",
        "--port", str(port),
        "-ngl", str(srv.get("ngl", 99)) if gpu else "0",
    ]
    args += list(srv.get("extra_args", []))
    return args


def _docker_logs(name: str, tail: int = 40) -> str:
    try:
        out = subprocess.run(
            ["docker", "logs", "--tail", str(tail), name],
            capture_output=True, text=True, timeout=15,
        )
        return (out.stdout + out.stderr).strip()
    except Exception:
        return "(logs unavailable)"


def _start_docker(gguf_path: str, port: int, config: dict, role: str,
                  image_override: str | None) -> ServerHandle:
    args = build_docker_run_args(gguf_path, port, config, role, image_override)
    name = f"redteam-{role}"
    print(f"Starting llama.cpp container {name} on :{port} "
          f"({'GPU' if '--device' in args else 'CPU'})")
    print(f"  cmd: {' '.join(args)}")

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as e:
        raise RuntimeError("docker CLI not found — is this a docker environment?") from e
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker run failed (code {proc.returncode}):\n{proc.stderr.strip()[-2000:]}"
        )

    timeouts = config.get("timeouts", {})
    startup_timeout = timeouts.get("startup", 300)  # GGUF load into VRAM is slow
    host = role_host(role)

    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        if is_healthy(port, ("/health", "/v1/models"), host=host):
            print(f"llama.cpp container {name} is ready ({host}:{port}).")
            return ServerHandle("docker", name, None)
        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=15,
        )
        if inspect.stdout.strip() != "true":
            logs = _docker_logs(name)
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            raise RuntimeError(f"container {name} exited early.\nlogs:\n{logs}")
        time.sleep(2)

    subprocess.run(["docker", "stop", "-t", "5", name], capture_output=True, timeout=60)
    logs = _docker_logs(name)
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
    raise RuntimeError(
        f"container {name} did not become healthy within {startup_timeout}s "
        f"(host={host}:{port})\nlogs:\n{logs}"
    )


# ── Local mode ─────────────────────────────────────────────────────

def _build_local_command(gguf_path: str, port: int, config: dict) -> list[str]:
    srv = config["server"]
    binary = srv.get("binary", "./llama.cpp/build/bin/llama-server")
    host = srv.get("host_bind", "127.0.0.1")
    ngl = srv.get("ngl", 99)
    extra = list(srv.get("extra_args", []))
    return [binary, "-m", gguf_path, "--host", host, "--port", str(port), "-ngl", str(ngl)] + extra


def _start_local(gguf_path: str, port: int, config: dict, role: str) -> ServerHandle:
    cmd = _build_local_command(gguf_path, port, config)
    timeouts = config.get("timeouts", {})
    startup_timeout = timeouts.get("startup", 300)

    print(f"Starting local llama-server on :{port}")
    print(f"  cmd: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    host = role_host(role)
    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        if is_healthy(port, ("/health", "/v1/models"), host=host):
            print(f"llama-server on {host}:{port} is ready.")
            return ServerHandle("local", "", proc)
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


# ── Public API ─────────────────────────────────────────────────────

def start_server(
    gguf_path: str,
    port: int,
    config: dict,
    role: str = "victim",
    image_override: str | None = None,
) -> ServerHandle:
    """Start a llama.cpp server for *role* ("victim" | "bf16") and wait until healthy.

    *image_override* ("cpu" | "gpu" | None) comes from per-tier config and
    wins over the global ``docker.gpu`` flag.
    """
    mode = config.get("server", {}).get("mode", "local")
    if mode == "docker":
        return _start_docker(gguf_path, port, config, role, image_override)
    return _start_local(gguf_path, port, config, role)


def stop_server(handle: ServerHandle | None, config: dict) -> None:
    """Stop a server (SIGTERM → SIGKILL locally, ``docker stop`` for containers)."""
    if handle is None:
        return

    timeouts = config.get("timeouts", {})
    shutdown_timeout = timeouts.get("shutdown", 30)
    gpu_release_delay = timeouts.get("gpu_release_delay", 5)

    if handle.kind == "docker":
        print(f"Stopping llama.cpp container {handle.name} ...")
        proc = subprocess.run(
            ["docker", "stop", "-t", str(shutdown_timeout), handle.name],
            capture_output=True, text=True, timeout=shutdown_timeout + 60,
        )
        subprocess.run(["docker", "rm", "-f", handle.name], capture_output=True, timeout=30)
        if proc.returncode != 0:
            print(f"  docker stop failed: {proc.stderr.strip()[:500]}")
        else:
            print(f"container {handle.name} stopped.")
    else:
        p = handle.proc
        if p is None or p.poll() is not None:
            return
        print("Stopping llama-server ...")
        p.terminate()
        try:
            p.wait(timeout=shutdown_timeout)
            print("llama-server stopped.")
        except subprocess.TimeoutExpired:
            print(f"  did not exit within {shutdown_timeout}s, sending SIGKILL ...")
            p.kill()
            p.wait()
            print("llama-server killed.")

    if gpu_release_delay > 0:
        print(f"  waiting {gpu_release_delay}s for GPU memory release ...")
        time.sleep(gpu_release_delay)
