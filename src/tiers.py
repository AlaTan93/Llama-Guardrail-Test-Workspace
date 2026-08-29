"""Quantization-tier resolution: the single home for tier → GGUF/image mapping.

Tiers are declared in ``src/e2e_config.yaml``::

    tiers:
      Q4_K_M: "model-Q4.gguf"                          # plain string
      Q2_K_CPU: {gguf: "model-Q2.gguf", image: cpu}    # dict with overrides

Every consumer (e2e orchestrator, web runners, CLI, system status) resolves
tiers through this module — never via private helpers elsewhere.
"""

from pathlib import Path

import yaml

DEFAULT_CONFIG = str(Path(__file__).parent / "e2e_config.yaml")


def load_config(config_path: str = DEFAULT_CONFIG) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tier_entry(config: dict, tier: str) -> tuple[str, str | None]:
    """``(gguf_filename, image_override)`` for *tier*; raises for unknown tiers.

    A tier value may be a plain GGUF filename or a dict with ``gguf`` plus
    optional ``image: cpu|gpu`` override.
    """
    tiers = config.get("tiers", {})
    if tier not in tiers:
        available = ", ".join(sorted(tiers))
        raise ValueError(f"Unknown tier '{tier}'. Available: {available}")
    value = tiers[tier]
    if isinstance(value, dict):
        return value.get("gguf"), value.get("image")
    return value, None


def tier_image(config: dict, tier: str) -> str | None:
    """Per-tier docker image override (``cpu`` | ``gpu`` | None)."""
    return tier_entry(config, tier)[1]


def resolve_gguf(tier: str, config: dict) -> str:
    """Absolute path to *tier*'s GGUF; raises if the file is missing."""
    gguf_file, _ = tier_entry(config, tier)
    if not gguf_file:
        raise ValueError(f"Tier '{tier}' has no gguf entry")
    models_dir = Path(config.get("models_dir", "./models"))
    gguf = str(models_dir / gguf_file)
    if not Path(gguf).exists():
        raise FileNotFoundError(f"GGUF not found: {gguf}")
    return gguf
