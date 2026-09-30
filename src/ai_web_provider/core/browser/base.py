"""Protocol describing a pluggable browser automation backend."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from collections.abc import Awaitable, Callable
from typing import Protocol

from playwright.async_api import BrowserContext, Page

from ai_web_provider.core.models import Account


class BrowserBackend(Protocol):
    """A backend capable of producing an isolated, session-persisted browser context."""

    def browser_context(self, account: Account) -> AbstractAsyncContextManager[BrowserContext]:
        """Yield a fresh `BrowserContext` for `account`, persisting state on exit."""
        ...

    async def close_all(self) -> None:
        """Close contexts still active during service shutdown."""
        ...

    async def interactive_login(
        self, account: Account, login_url: str, probe: Callable[[Page], Awaitable[bool]]
    ) -> bool:
        """Open headed Chromium, then save verified account cookies."""
        ...
