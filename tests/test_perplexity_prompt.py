"""Perplexity prompt fill/submit: fill the composer, thread-state submit."""

from __future__ import annotations

import asyncio

from ai_web_provider.providers.perplexity.page import prompt as prompt_module
from ai_web_provider.providers.perplexity.page import selectors as sel


class _FakeElement:
    def __init__(self, *, text: str = "filled", enabled: bool = True) -> None:
        self.clicked = False
        self.pressed: list[str] = []
        self.waited: list[str] = []
        self.filled: list[str] = []
        self._text = text
        self._enabled = enabled

    async def click(self) -> None:
        self.clicked = True

    async def press(self, key: str) -> None:
        self.pressed.append(key)

    async def wait_for(self, *, state: str) -> None:
        self.waited.append(state)

    async def fill(self, value: str) -> None:
        self.filled.append(value)

    async def inner_text(self) -> str:
        return self._text

    async def is_enabled(self) -> bool:
        return self._enabled


class _FakePage:
    def __init__(self) -> None:
        self.box = _FakeElement(text="filled")
        self.button = _FakeElement()

    def locator(self, selector: str) -> _FakeElement:
        if selector == sel.PROMPT_TEXTBOX:
            return self.box
        assert selector == sel.SUBMIT_BUTTON
        return self.button


def test_submit_prompt_fills_and_presses_enter_when_fresh() -> None:
    page = _FakePage()
    asyncio.run(prompt_module.submit_prompt(page, "hi", fresh=True))

    assert page.box.filled == ["hi"]
    assert page.box.pressed == ["Enter"]
    assert page.box.clicked is False
    assert page.button.clicked is False


def test_submit_prompt_fills_and_clicks_submit_when_resumed() -> None:
    page = _FakePage()
    asyncio.run(prompt_module.submit_prompt(page, "hi", fresh=False))

    assert page.box.filled == ["hi"]
    assert page.box.pressed == []
    assert page.box.clicked is False
    assert page.button.clicked is True


def test_submit_prompt_raises_when_fill_leaves_composer_empty() -> None:
    page = _FakePage()
    page.box = _FakeElement(text="   ")

    try:
        asyncio.run(prompt_module.submit_prompt(page, "hi", fresh=True))
    except RuntimeError as exc:
        assert "no visible composer text" in str(exc)
    else:
        raise AssertionError("expected RuntimeError on empty composer after fill")


def test_submit_prompt_raises_when_resumed_submit_disabled() -> None:
    page = _FakePage()
    page.button = _FakeElement(enabled=False)

    try:
        asyncio.run(prompt_module.submit_prompt(page, "hi", fresh=False))
    except RuntimeError as exc:
        assert "Submit is disabled" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when Submit is disabled")
