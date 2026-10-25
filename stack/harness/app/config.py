"""Harness configuration from environment (compose sets the defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/guardrails"
    )
    litellm_base_url: str = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")
    litellm_admin_url: str = os.environ.get("LITELLM_ADMIN_URL", "http://localhost:4000")
    litellm_api_key: str = os.environ.get("LITELLM_API_KEY", "")

    target_alias: str = os.environ.get("TARGET_ALIAS", "target-model")
    judge_aliases: list[str] = field(default_factory=lambda: _csv("JUDGE_ALIASES", "judge-self,judge-bf16,judge-claude"))
    primary_judge: str = os.environ.get("PRIMARY_JUDGE", "judge-claude")
    judge_temperature: float = float(os.environ.get("JUDGE_TEMPERATURE", "0.0"))

    max_run_concurrency: int = int(os.environ.get("MAX_RUN_CONCURRENCY", "16"))
    default_concurrency: int = int(os.environ.get("DEFAULT_CONCURRENCY", "4"))

    @property
    def default_judges(self) -> list[str]:
        return self.judge_aliases


settings = Settings()
