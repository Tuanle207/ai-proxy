"""Flow-specific authentication: interactive login, session checks, and re-login."""

from __future__ import annotations

from playwright.async_api import BrowserContext
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.base import BrowserBackend
from ai_proxy.core.errors import AIProxyError
from ai_proxy.core.models import Account, AccountStatus
from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.providers.google_flow.page.selectors import FLOW_URL, LOGIN_REDIRECT_HOST


class LoginTimeoutError(AIProxyError):
    """Raised when the user does not complete login within the allotted time."""


async def interactive_login(
    account: Account, manager: AccountManager, backend: BrowserBackend, *, timeout: float = 300.0
) -> Account:
    """Open a headed browser at Flow and wait for the user to finish Google login.

    On success, the browser context's storage state is persisted (by the backend, on
    context exit) and the account status is set to `active`. Raises `LoginTimeoutError`
    if the session is still on Google's sign-in page after `timeout` seconds.
    """
    async with backend.browser_context(account, headless=False) as context:
        page = await context.new_page()
        try:
            await page.goto(FLOW_URL)
            try:
                await page.wait_for_url(
                    lambda url: LOGIN_REDIRECT_HOST not in url, timeout=timeout * 1000
                )
                logged_in = True
            except PlaywrightTimeoutError:
                logged_in = False
        finally:
            await page.close()

    if not logged_in:
        raise LoginTimeoutError(
            f"login for {account.email} did not complete within {timeout}s"
        )
    return manager.set_status(account.email, AccountStatus.ACTIVE)


async def relogin(
    email: str, manager: AccountManager, backend: BrowserBackend, *, timeout: float = 300.0
) -> Account:
    """Force a fresh interactive login for an existing account, discarding any stale session."""
    account = manager.get(email)
    return await interactive_login(account, manager, backend, timeout=timeout)


async def is_logged_in(context: BrowserContext, *, timeout: float = 15.0) -> bool:
    """Navigate to the auth-gated app and check we weren't bounced to Google sign-in.

    Verified against a live session: an authenticated visit to `FLOW_URL` stays on
    `labs.google/...`, while an unauthenticated one redirects to `accounts.google.com`.
    """
    page = await context.new_page()
    try:
        await page.goto(FLOW_URL, timeout=timeout * 1000)
        return LOGIN_REDIRECT_HOST not in page.url
    finally:
        await page.close()


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
            return LOGIN_REDIRECT_HOST not in session.page.url
        async with self._backend.browser_context(session.account, headless=True) as context:
            page = await context.new_page()
            try:
                await page.goto(FLOW_URL, timeout=15 * 1000)
                return LOGIN_REDIRECT_HOST not in page.url
            finally:
                await page.close()

    async def interactive_login(self, session: ProviderSession) -> bool:
        async with self._backend.browser_context(session.account, headless=False) as context:
            page = await context.new_page()
            try:
                await page.goto(FLOW_URL)
                try:
                    await page.wait_for_url(
                        lambda url: LOGIN_REDIRECT_HOST not in url, timeout=300 * 1000
                    )
                    return True
                except PlaywrightTimeoutError:
                    return False
            finally:
                await page.close()

    async def probe_session(self, session: ProviderSession) -> bool:
        return await self.is_logged_in(session)
