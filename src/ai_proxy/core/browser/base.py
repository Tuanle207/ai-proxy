"""Protocol describing a pluggable browser automation backend."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from playwright.async_api import BrowserContext

from ai_proxy.core.models import Account


class BrowserBackend(Protocol):
    """A backend capable of producing an isolated, session-persisted browser context."""

    def browser_context(
        self, account: Account, *, headless: bool = True, reuse: bool = True
    ) -> AbstractAsyncContextManager[BrowserContext]:
        """Yield a `BrowserContext` for `account`, persisting its session state on exit.

        `reuse=False` forces a fresh, one-off browser (e.g. interactive login) even when the
        backend keeps warm sessions.
        """
        ...

    async def close_all(self) -> None:
        """Close any warm/pooled sessions held by this backend (service shutdown)."""
        ...

    async def close_account_sessions(self, email: str) -> None:
        """Close any warm/pooled sessions held for `email` (e.g. after an auth failure)."""
        ...
