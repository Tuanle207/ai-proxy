"""Convenience entrypoint for obtaining an account's browser context via the default backend."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager

from playwright.async_api import BrowserContext

from ai_proxy.core.browser.camoufox_backend import CamoufoxBackend
from ai_proxy.core.models import Account
from ai_proxy.core.paths import DataPaths


def account_browser(
    account: Account, paths: DataPaths, provider: str, *, headless: bool = True
) -> AbstractAsyncContextManager[BrowserContext]:
    """`async with account_browser(account, paths, provider) as context: ...`"""
    return CamoufoxBackend(paths, provider).browser_context(account, headless=headless)
