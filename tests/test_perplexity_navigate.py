"""Perplexity navigate tests: paginated thread-history load-wait before resuming a thread."""

from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_proxy.providers.perplexity.page import navigate as navigate_module


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.url = "https://www.perplexity.ai/rest/thread/test"
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        return self._payload


class _FakeExpectResponse:
    """Mimics `page.expect_response`'s async context manager: `.value` awaits to a response,
    or raises `PlaywrightTimeoutError` (on `__aexit__`, like the real Playwright API) when the
    queued page has none."""

    def __init__(self, response: _FakeResponse | None) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeExpectResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._response is None:
            raise PlaywrightTimeoutError("no matching response")

    @property
    def value(self) -> Any:
        async def _get() -> _FakeResponse:
            assert self._response is not None
            return self._response

        return _get()


class _FakePage:
    def __init__(self, pages: list[dict[str, Any] | None]) -> None:
        self._pages = list(pages)
        self.url = ""
        self.goto_calls: list[str] = []
        self.evaluate_calls: list[Any] = []

    async def goto(self, target: str, wait_until: str) -> None:
        self.goto_calls.append(target)
        self.url = target

    def expect_response(self, predicate: Any, timeout: float | None = None) -> _FakeExpectResponse:
        payload = self._pages.pop(0) if self._pages else None
        response = _FakeResponse(payload) if payload is not None else None
        return _FakeExpectResponse(response)

    async def evaluate(self, script: str, arg: Any = None) -> None:
        self.evaluate_calls.append(arg)


def test_single_page_skips_scrolling() -> None:
    page = _FakePage([{"entries": [1], "has_next_page": False}])
    asyncio.run(navigate_module._wait_for_thread_history_loaded(page, "target-url"))
    assert page.goto_calls == ["target-url"]
    assert page.evaluate_calls == []


def test_multi_page_scrolls_until_has_next_page_false() -> None:
    page = _FakePage(
        [
            {"entries": [1], "has_next_page": True},
            {"entries": [2], "has_next_page": True},
            {"entries": [3], "has_next_page": False},
        ]
    )
    asyncio.run(navigate_module._wait_for_thread_history_loaded(page, "target-url"))
    assert len(page.evaluate_calls) == 2


def test_no_initial_response_returns_without_raising() -> None:
    page = _FakePage([])
    asyncio.run(navigate_module._wait_for_thread_history_loaded(page, "target-url"))
    assert page.evaluate_calls == []


def test_stalled_scroll_stops_loop_without_raising() -> None:
    page = _FakePage([{"entries": [1], "has_next_page": True}, None])
    asyncio.run(navigate_module._wait_for_thread_history_loaded(page, "target-url"))
    assert len(page.evaluate_calls) == 1
