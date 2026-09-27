"""Perplexity answer-wait tests: completion via ask-complete and active stop state."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_web_provider.core.errors import GenerationTimeoutError
from ai_web_provider.providers.perplexity.page import selectors as sel
from ai_web_provider.providers.perplexity.page import wait as wait_module


class _FakeAnswersLocator:
    def __init__(self, *, count: int, text: str) -> None:
        self._count = count
        self._text = text

    async def count(self) -> int:
        return self._count

    @property
    def last(self) -> _FakeAnswersLocator:
        return self

    async def evaluate(self, script: str) -> str:
        return self._text


class _FakeStopLocator:
    def __init__(self, *, active_count: int = 0) -> None:
        self._active = active_count

    async def count(self) -> int:
        return self._active


class _FakeResponse:
    def __init__(self, *, url: str, ok: bool = True) -> None:
        self.url = url
        self.ok = ok


class _FakeExpectResponse:
    """Mimics `page.expect_response`: raises on `__aexit__` when nothing matched (see
    test_perplexity_navigate.py's `_FakeExpectResponse` for the same shape)."""

    def __init__(self, *, matched: bool) -> None:
        self._matched = matched

    async def __aenter__(self) -> _FakeExpectResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        if not self._matched:
            raise wait_module.PlaywrightTimeoutError("no matching response")


class _FakePage:
    def __init__(
        self,
        *,
        count: int,
        text: str,
        stop_active: int = 0,
        responses: list[_FakeResponse] | None = None,
    ) -> None:
        self.answers = _FakeAnswersLocator(count=count, text=text)
        self.stop = _FakeStopLocator(active_count=stop_active)
        self._responses = list(responses or [])

    def locator(self, selector: str) -> _FakeAnswersLocator | _FakeStopLocator:
        if selector == sel.ANSWER_BODY:
            return self.answers
        assert selector == sel.STOP_BUTTON_ACTIVE
        return self.stop

    def expect_response(self, predicate: Any, timeout: int) -> _FakeExpectResponse:
        for index, response in enumerate(self._responses):
            if predicate(response):
                self._responses.pop(index)
                return _FakeExpectResponse(matched=True)
        return _FakeExpectResponse(matched=False)


def _patch_poll(monkeypatch: Any) -> None:
    monkeypatch.setattr(wait_module, "_POLL_INTERVAL_SECONDS", 0.0)


def test_wait_for_answer_completes_when_ask_complete_arrives(monkeypatch: Any) -> None:
    _patch_poll(monkeypatch)
    page = _FakePage(
        count=2,
        text="new answer",
        responses=[_FakeResponse(url="https://www.perplexity.ai/rest/visitor/ask-complete")],
    )
    asyncio.run(
        wait_module.wait_for_answer(page, timeout=5.0, baseline_count=1, baseline_text="old")
    )


def test_wait_for_answer_ignores_non_matching_responses(monkeypatch: Any) -> None:
    _patch_poll(monkeypatch)
    page = _FakePage(
        count=1,
        text="new answer",
        responses=[_FakeResponse(url="https://www.perplexity.ai/rest/visitor/other")],
    )
    with pytest.raises(GenerationTimeoutError):
        asyncio.run(
            wait_module.wait_for_answer(page, timeout=0.1, baseline_count=1, baseline_text="old")
        )


def test_wait_for_answer_waits_while_streaming(monkeypatch: Any) -> None:
    _patch_poll(monkeypatch)
    page = _FakePage(
        count=2,
        text="new answer",
        stop_active=1,
        responses=[_FakeResponse(url="https://www.perplexity.ai/rest/visitor/ask-complete")],
    )
    with pytest.raises(GenerationTimeoutError):
        asyncio.run(
            wait_module.wait_for_answer(page, timeout=0.1, baseline_count=1, baseline_text="old")
        )


def test_wait_for_answer_times_out_when_no_new_answer(monkeypatch: Any) -> None:
    _patch_poll(monkeypatch)
    page = _FakePage(count=1, text="old")
    with pytest.raises(GenerationTimeoutError):
        asyncio.run(
            wait_module.wait_for_answer(page, timeout=0.1, baseline_count=1, baseline_text="old")
        )


def test_last_answer_text_empty_when_no_answers() -> None:
    page = _FakePage(count=0, text="")
    assert asyncio.run(wait_module.last_answer_text(page)) == ""
