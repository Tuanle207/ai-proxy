"""Shared ungoogled-chromium backend context tests without launching Chromium."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ai_web_provider.core.browser.ungoogled_chromium_backend import UngoogledChromiumBackend
from ai_web_provider.core.models import Account


class _Context:
    def __init__(self) -> None:
        self.closed = False


class _Runtime:
    def __init__(self) -> None:
        self.contexts: list[_Context] = []
        self.released: list[_Context] = []

    async def browser_context(self, *_: object) -> _Context:
        context = _Context()
        self.contexts.append(context)
        return context

    async def release_context(self, context: _Context) -> None:
        context.closed = True
        self.released.append(context)


def test_context_is_fresh_per_job_and_released_on_exit() -> None:
    async def run() -> None:
        runtime = _Runtime()
        backend = UngoogledChromiumBackend("google_flow", runtime)  # type: ignore[arg-type]
        account = Account(email="a@example.com")

        async with backend.browser_context(account) as first:
            assert first is runtime.contexts[0]
        async with backend.browser_context(account) as second:
            assert second is runtime.contexts[1]

        assert first is not second
        assert all(context.closed for context in runtime.contexts)
        assert backend._active_contexts == set()

    asyncio.run(run())


def test_close_all_releases_active_contexts() -> None:
    async def run() -> None:
        runtime = _Runtime()
        backend = UngoogledChromiumBackend("google_flow", runtime)  # type: ignore[arg-type]
        manager = backend.browser_context(Account(email="a@example.com"))
        await manager.__aenter__()
        await backend.close_all()

        assert runtime.contexts[0].closed
        assert backend._active_contexts == set()
        await manager.__aexit__(None, None, None)

    asyncio.run(run())
