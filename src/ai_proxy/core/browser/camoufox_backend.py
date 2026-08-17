"""Camoufox-backed implementation of `BrowserBackend`."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext

from ai_proxy.core.browser.proxy import validate_proxy_url
from ai_proxy.core.models import Account
from ai_proxy.core.paths import DataPaths


def build_launch_options(account: Account, *, headless: bool) -> dict[str, Any]:
    """Build Camoufox launch options for `account` (per-account proxy, humanized cursor)."""
    options: dict[str, Any] = {"headless": headless, "humanize": True}
    if account.proxy:
        options["proxy"] = {"server": validate_proxy_url(account.proxy)}
        options["geoip"] = True
    return options


class CamoufoxBackend:
    """Launches one Camoufox browser per account and persists its `storage_state.json`.

    Session cookies are provider-scoped (blocker 1.2.2): the same email on two providers
    must never overwrite each other's storage state, so the backend is constructed per
    provider and writes under `providers/<provider>/sessions/<email>/`.
    """

    def __init__(self, paths: DataPaths, provider: str):
        self._paths = paths
        self.provider = provider
        self._write_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, email: str) -> asyncio.Lock:
        email = email.strip().lower()
        lock = self._write_locks.get(email)
        if lock is None:
            lock = asyncio.Lock()
            self._write_locks[email] = lock
        return lock

    async def _persist_storage_state(self, account: Account, context: BrowserContext) -> None:
        """Serialize `storage_state.json` under a per-account lock, atomically (§1.2.4).

        Two contexts for the same account must never write the session file at once; a torn
        write surfaces later as a spurious `needs_login`. Writing to a temp file then
        `os.replace` mirrors `accounts/store.py`.
        """
        async with self._lock_for(account.email):
            self._paths.ensure_session_dir(self.provider, account.email)
            state_file = self._paths.storage_state_file(self.provider, account.email)
            tmp_file = state_file.with_name(state_file.name + ".tmp")
            await context.storage_state(path=str(tmp_file))
            os.replace(tmp_file, state_file)

    @asynccontextmanager
    async def browser_context(
        self, account: Account, *, headless: bool = True
    ) -> AsyncIterator[BrowserContext]:
        options = build_launch_options(account, headless=headless)
        state_file = self._paths.storage_state_file(self.provider, account.email)
        async with AsyncCamoufox(**options) as raw_browser:
            # persistent_context is not used above, so this is always a Browser.
            browser = cast(Browser, raw_browser)
            context_kwargs: dict[str, Any] = {}
            if state_file.is_file():
                context_kwargs["storage_state"] = str(state_file)
            context = await browser.new_context(**context_kwargs)
            try:
                yield context
            finally:
                await self._persist_storage_state(account, context)
                await context.close()
