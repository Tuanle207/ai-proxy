"""Perplexity prompt fill: fresh threads paste (fast), resumed threads type (slow but reliable)."""

from __future__ import annotations

import asyncio
from typing import Any

from ai_proxy.providers.perplexity.page import prompt as prompt_module
from ai_proxy.providers.perplexity.page import selectors as sel


class _FakeElement:
    def __init__(self) -> None:
        self.clicked = False

    async def click(self) -> None:
        self.clicked = True


class _FakePage:
    def __init__(self) -> None:
        self.box = _FakeElement()
        self.button = _FakeElement()

    def locator(self, selector: str) -> _FakeElement:
        if selector == sel.PROMPT_TEXTBOX:
            return self.box
        assert selector == sel.SUBMIT_BUTTON
        return self.button


def _patch_fill(monkeypatch: Any, calls: list[str]) -> None:
    async def _fake_paste_text(locator: Any, text: str) -> None:
        calls.append("paste")

    async def _fake_human_type(locator: Any, text: str) -> None:
        calls.append("type")

    async def _fake_human_delay(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(prompt_module, "paste_text", _fake_paste_text)
    monkeypatch.setattr(prompt_module, "human_type", _fake_human_type)
    monkeypatch.setattr(prompt_module, "human_delay", _fake_human_delay)


def test_submit_prompt_pastes_when_fresh(monkeypatch: Any) -> None:
    calls: list[str] = []
    _patch_fill(monkeypatch, calls)

    page = _FakePage()
    asyncio.run(prompt_module.submit_prompt(page, "hi", fresh=True))

    assert calls == ["paste"]
    assert page.box.clicked is True
    assert page.button.clicked is True


def test_submit_prompt_types_when_resumed(monkeypatch: Any) -> None:
    calls: list[str] = []
    _patch_fill(monkeypatch, calls)

    page = _FakePage()
    asyncio.run(prompt_module.submit_prompt(page, "hi", fresh=False))

    assert calls == ["type"]
    assert page.box.clicked is True
    assert page.button.clicked is True
