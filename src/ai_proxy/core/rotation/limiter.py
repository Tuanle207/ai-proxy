"""Per-account and global concurrency limiting."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ConcurrencyLimiter:
    """Bounds concurrent jobs per account (default 1) and optionally overall."""

    def __init__(self, *, per_account: int = 1, global_limit: int | None = None) -> None:
        self._per_account = per_account
        self._locks: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_account)
        )
        self._global = asyncio.Semaphore(global_limit) if global_limit else None

    @asynccontextmanager
    async def acquire(self, email: str) -> AsyncIterator[None]:
        async with self._locks[email]:
            if self._global is not None:
                async with self._global:
                    yield
            else:
                yield
