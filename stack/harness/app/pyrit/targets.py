"""Chat targets routed through the LiteLLM proxy."""

from __future__ import annotations

from pyrit.prompt_target import OpenAIChatTarget

from app.config import settings


def build_target(alias: str, *, temperature: float | None = None) -> OpenAIChatTarget:
    """A chat target for a LiteLLM alias. Judges pass temperature=0; the
    objective target under attack leaves sampling to the deployment."""
    return OpenAIChatTarget(
        endpoint=settings.litellm_base_url,
        api_key=settings.litellm_api_key or "not-needed",
        model_name=alias,
        temperature=temperature,
    )
