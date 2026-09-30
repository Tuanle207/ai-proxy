"""Shared ungoogled-chromium lifecycle with cookie-isolated job contexts."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from ai_web_provider.core.config import BrowserSettings
from ai_web_provider.core.models import Account
from ai_web_provider.core.paths import DataPaths


class UngoogledChromiumRuntimeManager:
    """Own one warm browser and create cookie-isolated contexts for all accounts."""

    def __init__(self, paths: DataPaths, settings: BrowserSettings):
        self._paths = paths
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: set[BrowserContext] = set()
        self._context_accounts: dict[BrowserContext, tuple[str, str]] = {}
        self._account_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._lock = asyncio.Lock()
        self._idle_close_task: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

    def _cancel_idle_close(self) -> None:
        if self._idle_close_task is not None:
            self._idle_close_task.cancel()
            self._idle_close_task = None

    def _account_lock(self, provider: str, account: Account) -> asyncio.Lock:
        key = (provider, account.email)
        lock = self._account_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._account_locks[key] = lock
        return lock

    async def _browser_for_context(self) -> Browser:
        await self.startup()
        async with self._lock:
            self._cancel_idle_close()
            if self._browser is None or not self._browser.is_connected():
                assert self._playwright is not None
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    executable_path=str(self._settings.ungoogled_chromium_executable),
                    args=["--no-first-run", "--no-default-browser-check"],
                    env={**os.environ, **self._settings.process_environment},
                    timeout=self._settings.startup_timeout_seconds * 1000,
                )
            return self._browser

    def _cookies_for(self, provider: str, email: str) -> list[dict[str, object]]:
        state_path = self._paths.storage_state_file(provider, email)
        if not state_path.is_file():
            return []
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        cookies = state.get("cookies") if isinstance(state, dict) else None
        return [cookie for cookie in cookies if isinstance(cookie, dict)] if isinstance(cookies, list) else []

    async def browser_context(self, provider: str, account: Account) -> BrowserContext:
        async with self._account_lock(provider, account):
            browser = await self._browser_for_context()
            cookies = self._cookies_for(provider, account.email)
            context = await browser.new_context(storage_state={"cookies": cookies})
            async with self._lock:
                self._contexts.add(context)
                self._context_accounts[context] = (provider, account.email)
            return context

    async def release_context(self, context: BrowserContext) -> None:
        try:
            await context.close()
        finally:
            async with self._lock:
                self._contexts.discard(context)
                self._context_accounts.pop(context, None)
                if not self._contexts and self._browser is not None:
                    self._cancel_idle_close()
                    self._idle_close_task = asyncio.create_task(self._close_when_idle())

    async def _close_when_idle(self) -> None:
        try:
            await asyncio.sleep(self._settings.idle_timeout_seconds)
            async with self._lock:
                if self._contexts:
                    return
                browser = self._browser
                self._browser = None
            if browser is not None:
                await browser.close()
        except asyncio.CancelledError:
            return

    async def _wait_for_account_contexts(self, provider: str, account: Account) -> None:
        key = (provider, account.email)
        while True:
            async with self._lock:
                if key not in self._context_accounts.values():
                    return
            await asyncio.sleep(0.1)

    @staticmethod
    def _write_cookies(path: Path, cookies: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps({"cookies": cookies}, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)

    async def interactive_login(
        self,
        provider: str,
        account: Account,
        login_url: str,
        probe: Callable[[Page], Awaitable[bool]],
    ) -> bool:
        """Open a headed browser and save its verified cookies for the account."""
        async with self._account_lock(provider, account):
            await self.startup()
            await self._wait_for_account_contexts(provider, account)
            assert self._playwright is not None
            browser = await self._playwright.chromium.launch(
                headless=False,
                executable_path=str(self._settings.ungoogled_chromium_executable),
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ],
                ignore_default_args=["--enable-automation"],
                env={**os.environ, **self._settings.process_environment},
                timeout=self._settings.startup_timeout_seconds * 1000,
            )
            context = await browser.new_context(
                viewport={"width": self._settings.viewport_width, "height": self._settings.viewport_height}
            )
            page = await context.new_page()
            try:
                await page.goto(login_url)
                deadline = asyncio.get_running_loop().time() + self._settings.login_timeout_seconds
                while not await probe(page):
                    if asyncio.get_running_loop().time() >= deadline:
                        return False
                    await asyncio.sleep(0.5)
                self._write_cookies(
                    self._paths.storage_state_file(provider, account.email), await context.cookies()
                )
                return True
            finally:
                await page.close()
                await context.close()
                await browser.close()

    async def shutdown(self) -> None:
        async with self._lock:
            self._cancel_idle_close()
            contexts = tuple(self._contexts)
            self._contexts.clear()
            self._context_accounts.clear()
            browser = self._browser
            self._browser = None
            playwright = self._playwright
            self._playwright = None
        await asyncio.gather(*(context.close() for context in contexts), return_exceptions=True)
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()
