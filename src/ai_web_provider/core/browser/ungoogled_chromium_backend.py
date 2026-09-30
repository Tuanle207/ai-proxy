"""Ungoogled-chromium browser-context creation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, Page

from ai_web_provider.core.models import Account
from ai_web_provider.runtime.ungoogled_chromium import UngoogledChromiumRuntimeManager


class UngoogledChromiumBackend:
    """Creates fresh cookie-isolated contexts in the shared browser."""

    def __init__(self, provider: str, runtime: UngoogledChromiumRuntimeManager):
        self.provider = provider
        self._runtime = runtime
        self._active_contexts: set[BrowserContext] = set()

    @asynccontextmanager
    async def browser_context(self, account: Account) -> AsyncIterator[BrowserContext]:
        context = await self._runtime.browser_context(self.provider, account)
        self._active_contexts.add(context)
        try:
            yield context
        finally:
            self._active_contexts.discard(context)
            await self._runtime.release_context(context)

    async def close_all(self) -> None:
        contexts = tuple(self._active_contexts)
        self._active_contexts.clear()
        await asyncio.gather(
            *(self._runtime.release_context(context) for context in contexts), return_exceptions=True
        )

    async def interactive_login(
        self, account: Account, login_url: str, probe: Callable[[Page], Awaitable[bool]]
    ) -> bool:
        return await self._runtime.interactive_login(self.provider, account, login_url, probe)
