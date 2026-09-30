"""Flow-specific authentication probes and headed Chromium login."""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_web_provider.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_web_provider.providers.google_flow.page import selectors as sel
from ai_web_provider.providers.google_flow.page.selectors import FLOW_URL, LOGIN_REDIRECT_HOST

_NETWORK_IDLE_TIMEOUT_MS = 10_000
_SETTLE_TIMEOUT_SECONDS = 5.0
_SETTLE_POLL_SECONDS = 0.5


async def is_logged_in(context: BrowserContext, *, timeout: float = 15.0) -> bool:
    """Navigate to the auth-gated app and check we weren't bounced to Google sign-in.

    Verified against a live session: an authenticated visit to `FLOW_URL` stays on
    `labs.google/...`, while an unauthenticated one redirects to `accounts.google.com`.
    """
    page = await context.new_page()
    try:
        await page.goto(FLOW_URL, timeout=timeout * 1000)
        return await probe_logged_in(page)
    finally:
        await page.close()


async def probe_logged_in(page: Page) -> bool:
    """True only once Flow's authenticated home actually renders the new-project button.

    A negative check ("URL isn't accounts.google.com yet") false-positives instantly on a
    fresh profile: Flow's SPA loads its shell before redirecting to Google sign-in via
    client-side JS, so this must wait for that redirect (or the authenticated home) to
    actually happen instead of trusting the URL at the instant `goto` returns — the same
    trap already documented in `providers/perplexity/auth.py`.
    """
    if LOGIN_REDIRECT_HOST in page.url:
        return False
    try:
        await page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass
    button = page.locator(sel.NEW_PROJECT_BUTTON)
    deadline = time.monotonic() + _SETTLE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if LOGIN_REDIRECT_HOST in page.url:
            return False
        if await button.count() > 0:
            return True
        await asyncio.sleep(_SETTLE_POLL_SECONDS)
    return False


class GoogleFlowAuth:
    """`AuthHandler` implementation: Flow's OAuth detection via the `accounts.google.com` probe.

    The redirect probe lives in this class (and the free `is_logged_in` above) because Flow's
    login detection is not reusable across providers — hence the `AuthHandler` seam.
    """

    def __init__(self, deps: ProviderRuntimeDeps):
        self._backend = deps.backend
        self._paths = deps.paths

    @property
    def login_url(self) -> str:
        return FLOW_URL

    async def is_logged_in(self, session: ProviderSession) -> bool:
        if session.page is not None:
            await session.page.goto(FLOW_URL, timeout=15 * 1000)
            return await probe_logged_in(session.page)
        async with self._backend.browser_context(session.account) as context:
            page = await context.new_page()
            try:
                await page.goto(FLOW_URL, timeout=15 * 1000)
                return await probe_logged_in(page)
            finally:
                await page.close()

    async def interactive_login(self, session: ProviderSession) -> bool:
        return await self._backend.interactive_login(session.account, FLOW_URL, probe_logged_in)

    async def probe_session(self, session: ProviderSession) -> bool:
        return await self.is_logged_in(session)
