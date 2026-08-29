"""Unit tests for the docker-mode llama.cpp launcher (no docker needed)."""

import pytest

from src import llama_server, tiers


@pytest.fixture
def config():
    return {
        "server": {
            "mode": "docker",
            "ngl": 99,
            "extra_args": ["-c", "4096"],
            "docker": {
                "image_gpu": "ghcr.io/ggml-org/llama.cpp:server-rocm@sha256:gpu",
                "image_cpu": "ghcr.io/ggml-org/llama.cpp:server@sha256:cpu",
                "network": "redteam",
                "models_dir_mount": "/models",
                "gpu": True,
                "publish": False,
                "gpu_env": {"HIP_VISIBLE_DEVICES": "0"},
            },
        },
        "models_dir": "./models",
        "tiers": {
            "Q4_K_M": "model-Q4.gguf",
            "Q2_CPU": {"gguf": "model-Q2.gguf", "image": "cpu"},
        },
        "timeouts": {"startup": 600, "shutdown": 30, "gpu_release_delay": 0},
    }


def test_gpu_run_args(config, monkeypatch, tmp_path):
    monkeypatch.setenv("HOST_PROJECT_ROOT", str(tmp_path))
    args = llama_server.build_docker_run_args("/x/models/model-Q4.gguf", 8080, config, "victim")
    assert args[:3] == ["docker", "run", "-d"]
    assert "--name" in args and args[args.index("--name") + 1] == "redteam-victim"
    assert args[args.index("--network") + 1] == "redteam"
    # models dir is bind-mounted read-only at the container mount point
    v_idx = args.index("-v")
    assert args[v_idx + 1].endswith(":/models:ro")
    # GPU flags + image + model path
    assert "--device" in args and "/dev/kfd" in args
    e_idx = args.index("--env")
    assert args[e_idx + 1] == "HIP_VISIBLE_DEVICES=0"
    assert "ghcr.io/ggml-org/llama.cpp:server-rocm@sha256:gpu" in args
    m_idx = args.index("-m")
    assert args[m_idx + 1] == "/models/model-Q4.gguf"
    ngl_idx = args.index("-ngl")
    assert args[ngl_idx + 1] == "99"
    assert args[args.index("--port") + 1] == "8080"
    assert args[-2:] == ["-c", "4096"]  # extra_args appended
    # no publish by default
    assert "-p" not in args


def test_cpu_override_run_args(config):
    args = llama_server.build_docker_run_args(
        "/x/models/model-Q2.gguf", 8081, config, "bf16", image_override="cpu"
    )
    assert "--device" not in args and "/dev/kfd" not in args
    assert "ghcr.io/ggml-org/llama.cpp:server@sha256:cpu" in args
    assert args[args.index("-ngl") + 1] == "0"
    assert args[args.index("--name") + 1] == "redteam-bf16"


def test_gpu_disabled_global(config):
    config["server"]["docker"]["gpu"] = False
    args = llama_server.build_docker_run_args("/x/models/m.gguf", 8080, config, "victim")
    assert "--device" not in args
    assert "ghcr.io/ggml-org/llama.cpp:server@sha256:cpu" in args


def test_publish_flag(config):
    config["server"]["docker"]["publish"] = True
    args = llama_server.build_docker_run_args("/x/models/m.gguf", 8080, config, "victim")
    p_idx = args.index("-p")
    assert args[p_idx + 1] == "8080:8080"


def test_tier_entry_dict_and_string(config):
    gguf, image = tiers.tier_entry(config, "Q4_K_M")
    assert gguf == "model-Q4.gguf" and image is None
    gguf, image = tiers.tier_entry(config, "Q2_CPU")
    assert gguf == "model-Q2.gguf" and image == "cpu"
    assert tiers.tier_image(config, "Q2_CPU") == "cpu"
    assert tiers.tier_image(config, "Q4_K_M") is None


def test_tier_entry_unknown_raises(config):
    with pytest.raises(ValueError, match="Unknown tier"):
        tiers.tier_entry(config, "NOPE")


def test_select_image_rules():
    dock = {"image_gpu": "gpu-img", "image_cpu": "cpu-img", "gpu": True}
    assert llama_server.select_image(dock, None) == ("gpu-img", True)
    assert llama_server.select_image(dock, "cpu") == ("cpu-img", False)
    assert llama_server.select_image(dock, "gpu") == ("gpu-img", True)
    dock["gpu"] = False
    assert llama_server.select_image(dock, None) == ("cpu-img", False)
    assert llama_server.select_image(dock, "gpu") == ("gpu-img", True)  # override wins


def test_role_host_env(monkeypatch):
    monkeypatch.delenv("VICTIM_HOST", raising=False)
    assert llama_server.role_host("victim") == "127.0.0.1"
    monkeypatch.setenv("VICTIM_HOST", "redteam-victim")
    assert llama_server.role_host("victim") == "redteam-victim"
    assert llama_server.role_host("bf16") == "127.0.0.1"


def test_host_models_dir(monkeypatch, config):
    monkeypatch.setenv("HOST_PROJECT_ROOT", "/srv/repo")
    assert llama_server.host_models_dir(config) == "/srv/repo/models"


def test_host_models_dir_requires_hint_in_container(monkeypatch, tmp_path):
    monkeypatch.delenv("HOST_PROJECT_ROOT", raising=False)
    monkeypatch.setattr(llama_server.Path, "exists", lambda self: str(self) == "/.dockerenv")
    monkeypatch.setattr(llama_server, "_bind_source", lambda p: None)
    with pytest.raises(RuntimeError, match="HOST_PROJECT_ROOT"):
        llama_server.host_models_dir({"models_dir": str(tmp_path)})
