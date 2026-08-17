"""Perplexity authentication (AuthHandler).

Logged-in probe confirmed via `scripts/recon_perplexity.py --inspect` (2026-08-17): the
notification bell (`#pplx-icon-bell`) renders only for authenticated users; the logged-out
sidebar instead exposes a "Sign In" control.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.providers.perplexity.config import PerplexitySettings
from ai_proxy.providers.perplexity.page import selectors as sel

_NETWORK_IDLE_TIMEOUT_MS = 10_000
_SETTLE_TIMEOUT_SECONDS = 5.0
_SETTLE_POLL_SECONDS = 0.5


async def probe_logged_in(page: Page) -> bool:
    """True when the session looks authenticated: the notification bell icon is rendered.

    The bell (`use[xlink:href="#pplx-icon-bell"]`) only exists for logged-in users — a
    *positive* marker, unlike the old "Sign In is absent" check which read 0 right after
    `domcontentloaded`, before React mounted the sidebar (observed live as
    `interactive_login` "succeeding" instantly with nothing typed). So wait for the network
    to settle first, then poll briefly for the bell to appear; if it never does within the
    settle window, report logged out — a false `needs_login` is cheap to re-check, a false
    "logged in" silently breaks every run that trusts it.
    """
    if "perplexity.ai" not in page.url:
        return False
    try:
        await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass
    bell = page.locator(sel.LOGGED_IN_BELL)
    deadline = time.monotonic() + _SETTLE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if await bell.count() > 0:
            return True
        await asyncio.sleep(_SETTLE_POLL_SECONDS)
    return False


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
