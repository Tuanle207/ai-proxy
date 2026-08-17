"""Perplexity authentication (AuthHandler).

Confirmed via `scripts/recon_perplexity.py --inspect` (2026-08-17): the logged-out sidebar
exposes a "Sign In" control that disappears once authenticated.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast

from playwright.async_api import Page

from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.providers.perplexity.config import PerplexitySettings
from ai_proxy.providers.perplexity.page import selectors as sel


async def probe_logged_in(page: Page) -> bool:
    """True when the session looks authenticated: on Perplexity with no "Sign In" control."""
    if "perplexity.ai" not in page.url:
        return False
    return await page.locator(sel.LOGIN_BUTTON).count() == 0


class PerplexityAuth:
    """`AuthHandler` implementation: interactive login + logged-in probe."""

    def __init__(self, deps: ProviderRuntimeDeps):
        self._deps = deps
        self._settings = cast(PerplexitySettings, deps.settings)

    @property
    def login_url(self) -> str:
        return sel.PERPLEXITY_URL

    async def is_logged_in(self, session: ProviderSession) -> bool:
        if session.page is not None:
            await session.page.goto(sel.PERPLEXITY_URL, wait_until="domcontentloaded")
            return await probe_logged_in(session.page)
        async with self._deps.backend.browser_context(session.account, headless=True) as context:
            page = await context.new_page()
            try:
                await page.goto(sel.PERPLEXITY_URL, wait_until="domcontentloaded")
                return await probe_logged_in(page)
            finally:
                await page.close()

    async def interactive_login(self, session: ProviderSession) -> bool:
        timeout = self._settings.login_timeout
        async with self._deps.backend.browser_context(session.account, headless=False) as context:
            page = await context.new_page()
            try:
                await page.goto(sel.PERPLEXITY_URL, wait_until="domcontentloaded")
                return await self._wait_logged_in(page, timeout)
            finally:
                await page.close()

    async def probe_session(self, session: ProviderSession) -> bool:
        return await self.is_logged_in(session)

    async def _wait_logged_in(self, page: Page, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await probe_logged_in(page):
                return True
            await asyncio.sleep(0.5)
        return False
