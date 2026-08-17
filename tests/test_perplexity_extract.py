"""Perplexity answer-extraction tests: Copy-button capture + markdown citation stripping.

Fake page/locators only — no browser. The copy flow is: hook `writeText`, dispatch a click
on the last Copy button, poll `window.__pplx_copy`, then strip citation markers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_proxy.providers.perplexity.errors import PerplexityError
from ai_proxy.providers.perplexity.page import extract as extract_module
from ai_proxy.providers.perplexity.page import selectors as sel


class FakeCopyButton:
    def __init__(self, present: bool = True):
        self._present = present
        self.dispatched: list[str] = []

    async def count(self) -> int:
        return 1 if self._present else 0

    async def dispatch_event(self, event: str) -> None:
        self.dispatched.append(event)


class FakeCopyLocator:
    def __init__(self, button: FakeCopyButton):
        self._button = button

    @property
    def last(self) -> FakeCopyButton:
        return self._button


class FakeCopyPage:
    """`evaluate` distinguishes the three scripts by their content."""

    def __init__(self, copied: str | None, button: FakeCopyButton):
        self.url = "https://www.perplexity.ai/search/abc"
        self.copied = copied
        self.button = button

    def locator(self, selector: str) -> FakeCopyLocator:
        assert selector == sel.COPY_BUTTON
        return FakeCopyLocator(self.button)

    async def evaluate(self, script: str) -> Any:
        if "writeText" in script or "__pplx_copy = null" in script:
            return None
        return self.copied


def test_extract_answer_copies_and_strips(monkeypatch: Any) -> None:
    monkeypatch.setattr(extract_module, "_COPY_POLL_SECONDS", 0.0)
    button = FakeCopyButton()
    page = FakeCopyPage("Answer [1](https://example.com/src) , see [2, 3] too.", button)
    result = asyncio.run(extract_module.extract_answer(page))
    assert result == "Answer, see too."
    assert button.dispatched == ["click"]


def test_extract_answer_missing_button_raises() -> None:
    page = FakeCopyPage("text", FakeCopyButton(present=False))
    with pytest.raises(PerplexityError):
        asyncio.run(extract_module.extract_answer(page))


def test_extract_answer_no_text_times_out(monkeypatch: Any) -> None:
    monkeypatch.setattr(extract_module, "_COPY_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(extract_module, "_COPY_POLL_SECONDS", 0.0)
    page = FakeCopyPage(None, FakeCopyButton())
    with pytest.raises(PerplexityError):
        asyncio.run(extract_module.extract_answer(page))


def test_strip_citations_variants() -> None:
    strip = extract_module.strip_citations
    assert strip("keep [1](https://a.io/x) this") == "keep this"
    assert strip("bare [12] marker") == "bare marker"
    assert strip("grouped [2,3](https://a.io) tail") == "grouped tail"
    assert strip("real [link](https://a.io) stays") == "real [link](https://a.io) stays"
    assert strip("code:\n\n    indented [1](https://a.io) block") == (
        "code:\n\n    indented block"
    )
