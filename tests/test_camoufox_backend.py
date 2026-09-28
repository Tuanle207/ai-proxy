"""`CamoufoxBackend` per-job context tests (no real browser launched)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ai_web_provider.core.browser.camoufox_backend import CamoufoxBackend
from ai_web_provider.core.models import Account
from ai_web_provider.core.paths import DataPaths


class _Context:
    def __init__(self, *, fail_persist: bool = False) -> None:
        self.closed = False
        self.fail_persist = fail_persist

    async def storage_state(self, *, path: str) -> None:
        if self.fail_persist:
            raise RuntimeError("cannot persist")
        Path(path).write_text("{}", encoding="utf-8")

    async def close(self) -> None:
        self.closed = True


class _Browser:
    def __init__(self, contexts: list[_Context]) -> None:
        self.contexts = contexts

    def is_connected(self) -> bool:
        return True

    async def new_context(self, **_: object) -> _Context:
        context = _Context()
        self.contexts.append(context)
        return context


def _backend(tmp_path: Path) -> tuple[CamoufoxBackend, list[_Context]]:
    contexts: list[_Context] = []
    backend = CamoufoxBackend(DataPaths(tmp_path), "google_flow")
    backend.set_browser(_Browser(contexts))  # type: ignore[arg-type]
    return backend, contexts


def test_context_is_fresh_per_job_and_closed_on_exit(tmp_path: Path) -> None:
    async def run() -> None:
        backend, contexts = _backend(tmp_path)
        account = Account(email="a@example.com")

        async with backend.browser_context(account) as first:
            assert first is contexts[0]
        async with backend.browser_context(account) as second:
            assert second is contexts[1]

        assert first is not second
        assert all(context.closed for context in contexts)
        assert backend._active_contexts == set()
        assert backend._paths.storage_state_file("google_flow", account.email).is_file()

    asyncio.run(run())


def test_context_closes_when_persistence_fails(tmp_path: Path) -> None:
    async def run() -> None:
        backend, _ = _backend(tmp_path)
        context = _Context(fail_persist=True)

        class _FailingBrowser:
            def is_connected(self) -> bool:
                return True

            async def new_context(self, **_: object) -> _Context:
                return context

        backend.set_browser(_FailingBrowser())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="cannot persist"):
            async with backend.browser_context(Account(email="a@example.com")):
                pass
        assert context.closed
        assert backend._active_contexts == set()

    asyncio.run(run())


def test_context_requires_started_browser(tmp_path: Path) -> None:
    async def run() -> None:
        backend = CamoufoxBackend(DataPaths(tmp_path), "google_flow")
        with pytest.raises(RuntimeError, match="not started"):
            async with backend.browser_context(Account(email="a@example.com")):
                pass

    asyncio.run(run())


def test_context_rejects_account_proxy(tmp_path: Path) -> None:
    async def run() -> None:
        backend, _ = _backend(tmp_path)
        with pytest.raises(RuntimeError, match="proxies are unsupported"):
            async with backend.browser_context(Account(email="a@example.com", proxy="http://proxy")):
                pass

    asyncio.run(run())
