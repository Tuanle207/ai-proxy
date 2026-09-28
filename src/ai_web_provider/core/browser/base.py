"""Protocol describing a pluggable browser automation backend."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from playwright.async_api import Browser, BrowserContext

from ai_web_provider.core.models import Account


class BrowserBackend(Protocol):
    """A backend capable of producing an isolated, session-persisted browser context."""

    @property
    def headless(self) -> bool:
        """Whether the container-owned browser runs without a visible window."""
        ...

    def set_browser(self, browser: Browser | None) -> None:
        """Attach the container-owned browser while the runtime is started."""
        ...

    def browser_context(self, account: Account) -> AbstractAsyncContextManager[BrowserContext]:
        """Yield a fresh `BrowserContext` for `account`, persisting state on exit."""
        ...

    async def close_all(self) -> None:
        """Close contexts still active during service shutdown."""
        ...
