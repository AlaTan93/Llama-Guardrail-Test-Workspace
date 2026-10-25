"""PyRIT process lifecycle: initialize once, IN_MEMORY, silent."""

from __future__ import annotations

import asyncio

_initialized = False
_lock = asyncio.Lock()


async def ensure_pyrit() -> None:
    """Initialize PyRIT once per process.

    PyRIT memory stays in-process (IN_MEMORY); Postgres is the system of
    record, so nothing needs a persistent PyRIT memory backend.
    """
    global _initialized
    if _initialized:
        return
    async with _lock:
        if _initialized:
            return
        from pyrit.setup import IN_MEMORY, initialize_pyrit_async

        await initialize_pyrit_async(memory_db_type=IN_MEMORY, silent=True)
        _initialized = True
