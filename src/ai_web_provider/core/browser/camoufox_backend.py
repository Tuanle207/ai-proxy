"""Camoufox-backed browser-context creation and storage-state persistence."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from playwright.async_api import Browser, BrowserContext

from ai_web_provider.core.models import Account
from ai_web_provider.core.paths import DataPaths


class CamoufoxBackend:
    """Creates one isolated context per job from a container-owned browser."""

    def __init__(self, paths: DataPaths, provider: str):
        self._paths = paths
        self.provider = provider
        self._browser: Browser | None = None
        self._headless = True
        self._write_locks: dict[str, asyncio.Lock] = {}
        self._active_contexts: set[BrowserContext] = set()

    @property
    def headless(self) -> bool:
        return self._headless

    def set_browser(self, browser: Browser | None, *, headless: bool = True) -> None:
        """Attach the browser while its runtime container is started."""
        self._browser = browser
        self._headless = headless

    def _lock_for(self, email: str) -> asyncio.Lock:
        email = email.strip().lower()
        lock = self._write_locks.get(email)
        if lock is None:
            lock = asyncio.Lock()
            self._write_locks[email] = lock
        return lock

    async def _persist_storage_state(self, account: Account, context: BrowserContext) -> None:
        """Atomically persist state without concurrent writes for one account."""
        async with self._lock_for(account.email):
            self._paths.ensure_session_dir(self.provider, account.email)
            state_file = self._paths.storage_state_file(self.provider, account.email)
            tmp_file = state_file.with_name(state_file.name + ".tmp")
            await context.storage_state(path=str(tmp_file))
            os.replace(tmp_file, state_file)

    @asynccontextmanager
    async def browser_context(self, account: Account) -> AsyncIterator[BrowserContext]:
        """Yield a fresh context and close it when this job attempt completes."""
        if account.proxy:
            raise RuntimeError("account proxies are unsupported by the shared browser runtime")
        browser = self._browser
        if browser is None or not browser.is_connected():
            raise RuntimeError("browser runtime is not started or has disconnected")

        state_file = self._paths.storage_state_file(self.provider, account.email)
        context_kwargs: dict[str, Any] = {}
        if state_file.is_file():
            context_kwargs["storage_state"] = str(state_file)
        context = await browser.new_context(**context_kwargs)
        self._active_contexts.add(context)
        try:
            yield context
        finally:
            try:
                await self._persist_storage_state(account, context)
            finally:
                self._active_contexts.discard(context)
                await context.close()

    async def close_all(self) -> None:
        """Defensively close contexts that are still active during shutdown."""
        contexts = tuple(self._active_contexts)
        self._active_contexts.clear()
        for context in contexts:
            await context.close()
