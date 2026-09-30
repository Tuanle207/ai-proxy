"""Cookie state and idle lifecycle tests without launching Chromium."""

from __future__ import annotations

import asyncio
import json

from ai_web_provider.core.config import BrowserSettings
from ai_web_provider.core.models import Account
from ai_web_provider.core.paths import DataPaths
from ai_web_provider.runtime.ungoogled_chromium import UngoogledChromiumRuntimeManager


class _Context:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _Browser:
    def __init__(self) -> None:
        self.closed = False
        self.states: list[object] = []

    def is_connected(self) -> bool:
        return not self.closed

    async def new_context(self, *, storage_state: object) -> _Context:
        self.states.append(storage_state)
        return _Context()

    async def close(self) -> None:
        self.closed = True


class _Chromium:
    def __init__(self) -> None:
        self.browser = _Browser()
        self.launches = 0

    async def launch(self, **_: object) -> _Browser:
        self.launches += 1
        return self.browser


class _Playwright:
    def __init__(self) -> None:
        self.chromium = _Chromium()


def test_contexts_restore_the_requested_account_cookies(tmp_path) -> None:
    async def run() -> None:
        paths = DataPaths(tmp_path)
        settings = BrowserSettings(idle_timeout_seconds=60)
        runtime = UngoogledChromiumRuntimeManager(paths, settings)
        playwright = _Playwright()
        runtime._playwright = playwright  # type: ignore[assignment]
        account = Account(email="a@example.com")
        state_path = paths.storage_state_file("google_flow", account.email)
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"cookies": [{"name": "SID", "value": "x"}]}))

        context = await runtime.browser_context("google_flow", account)

        assert playwright.chromium.launches == 1
        assert playwright.chromium.browser.states == [{"cookies": [{"name": "SID", "value": "x"}]}]
        await runtime.release_context(context)
        await runtime.shutdown()

    asyncio.run(run())


def test_idle_timeout_closes_shared_browser(tmp_path) -> None:
    async def run() -> None:
        runtime = UngoogledChromiumRuntimeManager(
            DataPaths(tmp_path), BrowserSettings(idle_timeout_seconds=0)
        )
        playwright = _Playwright()
        runtime._playwright = playwright  # type: ignore[assignment]

        context = await runtime.browser_context("google_flow", Account(email="a@example.com"))
        await runtime.release_context(context)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert playwright.chromium.browser.closed
        await runtime.shutdown()

    asyncio.run(run())


def test_cookie_writer_stores_cookies_only(tmp_path) -> None:
    path = tmp_path / "storage_state.json"
    UngoogledChromiumRuntimeManager._write_cookies(path, [{"name": "SID", "value": "x"}])
    assert json.loads(path.read_text()) == {"cookies": [{"name": "SID", "value": "x"}]}
