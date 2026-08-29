"""Unified server lifecycle: llama.cpp servers + the LiteLLM proxy.

One place owns every process/container the pipeline needs.  Callers declare
what they need and get a :class:`ServerStack` that starts it all and tears it
down in reverse order — replacing the start/try/finally pattern that was
previously repeated across the e2e orchestrator and web runners.

Usage::

    # victim llama server + LiteLLM proxy, auto-torn-down:
    async with ServerStack(config, victim_tier="Q4_K_M") as stack:
        ...

    # e2e's GPU schedule — proxy held across both llama phases:
    async with ServerStack(config, proxy=True) as outer:
        async with ServerStack(config, victim_tier=tier, proxy=False) as phase_a:
            ...  # attacks + victim self-scoring
        async with ServerStack(config, bf16=True, proxy=False) as phase_b:
            ...  # external scoring
"""

import asyncio
import subprocess

import src.litellm_proxy as litellm_proxy
import src.llama_server as llama_server
from src import tiers


class ServerStack:
    """Async context manager owning llama.cpp servers and the LiteLLM proxy.

    Args:
        config: e2e config dict (``src/tiers.load_config``).
        victim_tier: tier name — starts the victim llama server for that tier.
        bf16: start the BF16 reference judge on the ``bf16`` port.
        proxy: ensure the LiteLLM proxy is up (skipped when already healthy;
            external/compose-managed proxies are never spawned, just awaited).
    """

    def __init__(self, config: dict, victim_tier: str | None = None,
                 bf16: bool = False, proxy: bool = True):
        self.config = config
        self.victim_tier = victim_tier
        self.bf16 = bf16
        self.proxy = proxy
        self._proxy_proc: subprocess.Popen | None = None
        self._llama_handles: list[llama_server.ServerHandle] = []

    # ── context manager ──
    async def __aenter__(self) -> "ServerStack":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    # ── lifecycle ──
    async def start(self) -> None:
        if self.proxy:
            self._proxy_proc = await asyncio.to_thread(litellm_proxy.start_litellm_proxy)

        if self.victim_tier:
            gguf = tiers.resolve_gguf(self.victim_tier, self.config)
            handle = await asyncio.to_thread(
                llama_server.start_server, gguf, self.config["ports"]["victim"], self.config,
                "victim", tiers.tier_image(self.config, self.victim_tier),
            )
            self._llama_handles.append(handle)

        if self.bf16:
            gguf = tiers.resolve_gguf("BF16", self.config)
            handle = await asyncio.to_thread(
                llama_server.start_server, gguf, self.config["ports"]["bf16"], self.config,
                "bf16", tiers.tier_image(self.config, "BF16"),
            )
            self._llama_handles.append(handle)

    async def stop(self) -> None:
        for handle in reversed(self._llama_handles):
            await asyncio.to_thread(llama_server.stop_server, handle, self.config)
        self._llama_handles.clear()
        if self._proxy_proc is not None:
            self._proxy_proc.terminate()
            self._proxy_proc = None
