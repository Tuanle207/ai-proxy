"""Perplexity answer-extraction tests: Copy-button capture + markdown citation stripping.

Fake page/locators only — no browser. The copy flow is: hook `writeText`, dispatch a click
on the last Copy button, poll `window.__pplx_copy`, then strip citation markers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ai_web_provider.providers.perplexity.errors import PerplexityError
from ai_web_provider.providers.perplexity.page import extract as extract_module
from ai_web_provider.providers.perplexity.page import selectors as sel


class FakeCopyButton:
    def __init__(self, present: bool = True):
        self._present = present
        self.dispatched: list[str] = []

    async def count(self) -> int:
        return 1 if self._present else 0

    async def dispatch_event(self, event: str) -> None:
        self.dispatched.append(event)


class FakeStopLocator:
    def __init__(self, streaming: bool = False):
        self._streaming = streaming

    async def count(self) -> int:
        return 1 if self._streaming else 0


class FakeCopyLocator:
    def __init__(self, button: FakeCopyButton):
        self._button = button

    @property
    def last(self) -> FakeCopyButton:
        return self._button


class FakeArtifactIcon:
    def __init__(self, present: bool):
        self._present = present
        self.dispatched: list[str] = []

    async def count(self) -> int:
        return 1 if self._present else 0

    async def dispatch_event(self, event: str) -> None:
        self.dispatched.append(event)


class FakeArtifactIconLocator:
    def __init__(self, icon: FakeArtifactIcon):
        self._icon = icon

    @property
    def last(self) -> FakeArtifactIcon:
        return self._icon

    async def count(self) -> int:
        return await self._icon.count()


class FakeTurnScope:
    """Backs `page.locator(RESPONSE_LIST_CONTAINER).first.locator('> div').last`."""

    def __init__(self, icon: FakeArtifactIcon):
        self._icon = icon

    @property
    def first(self) -> FakeTurnScope:
        return self

    @property
    def last(self) -> FakeTurnScope:
        return self

    def locator(self, selector: str) -> FakeArtifactIconLocator | FakeTurnScope:
        if selector == sel.FILE_ARTIFACT_ICON:
            return FakeArtifactIconLocator(self._icon)
        assert selector == "> div"
        return self


class FakeArtifactPanel:
    def __init__(self, text: str | None, *, times_out: bool = False):
        self._text = text
        self._times_out = times_out

    async def wait_for(self, *, state: str, timeout: int) -> None:
        if self._times_out:
            raise PlaywrightTimeoutError("panel never opened")

    async def inner_text(self) -> str:
        assert self._text is not None
        return self._text


class FakeArtifactPanelLocator:
    def __init__(self, panel: FakeArtifactPanel):
        self._panel = panel

    @property
    def last(self) -> FakeArtifactPanel:
        return self._panel


class FakeCopyPage:
    """`evaluate` distinguishes the three scripts by their content."""

    def __init__(
        self,
        copied: str | None,
        button: FakeCopyButton,
        *,
        streaming: bool = False,
        artifact_icon_present: bool = False,
        artifact_panel_text: str | None = None,
        artifact_panel_times_out: bool = False,
    ):
        self.url = "https://www.perplexity.ai/search/abc"
        self.copied = copied
        self.button = button
        self.stop = FakeStopLocator(streaming=streaming)
        self.icon = FakeArtifactIcon(present=artifact_icon_present)
        self.panel = FakeArtifactPanel(artifact_panel_text, times_out=artifact_panel_times_out)

    def locator(
        self, selector: str
    ) -> (
        FakeCopyLocator | FakeStopLocator | FakeArtifactIconLocator | FakeArtifactPanelLocator
        | FakeTurnScope
    ):
        if selector == sel.STOP_BUTTON_ACTIVE:
            return self.stop
        if selector == sel.RESPONSE_LIST_CONTAINER:
            return FakeTurnScope(self.icon)
        if selector == sel.ARTIFACT_PANEL:
            return FakeArtifactPanelLocator(self.panel)
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


def test_extract_answer_still_streaming_raises(monkeypatch: Any) -> None:
    monkeypatch.setattr(extract_module, "_STREAM_STOP_TIMEOUT_SECONDS", 0.0)
    page = FakeCopyPage("text", FakeCopyButton(), streaming=True)
    with pytest.raises(PerplexityError):
        asyncio.run(extract_module.extract_answer(page))


def test_extract_answer_uses_file_artifact_when_icon_present() -> None:
    page = FakeCopyPage(
        "text",
        FakeCopyButton(),
        artifact_icon_present=True,
        artifact_panel_text="generated file contents [1](https://example.com)",
    )
    result = asyncio.run(extract_module.extract_answer(page))
    assert result == "generated file contents [1](https://example.com)"
    assert page.icon.dispatched == ["click"]
    assert page.button.dispatched == []


def test_extract_file_artifact_panel_timeout_raises() -> None:
    page = FakeCopyPage(
        "text", FakeCopyButton(), artifact_icon_present=True, artifact_panel_times_out=True
    )
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
