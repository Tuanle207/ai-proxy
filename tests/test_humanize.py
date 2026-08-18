"""`human_type` must not send raw `\n` as a bare Enter keystroke (submits prematurely on
composers like Perplexity's that treat Enter as "send")."""

from __future__ import annotations

import asyncio
from typing import Any

from ai_proxy.core.browser.humanize import human_type, paste_text


class _FakeLocator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def press_sequentially(self, char: str, *, delay: float) -> None:
        self.calls.append(("press_sequentially", char))

    async def press(self, key: str, *, delay: float) -> None:
        self.calls.append(("press", key))

    async def evaluate(self, script: str, arg: Any) -> None:
        self.calls.append(("evaluate", arg))
        self.last_script = script


def test_human_type_sends_shift_enter_for_newlines() -> None:
    locator = _FakeLocator()
    asyncio.run(human_type(locator, "line one\nline two", min_delay_ms=0, max_delay_ms=0))

    assert ("press", "Shift+Enter") in locator.calls
    assert ("press_sequentially", "\n") not in locator.calls
    assert [call for call in locator.calls if call[0] == "press_sequentially"] == [
        ("press_sequentially", c) for c in "line one" + "line two"
    ]


def test_paste_text_dispatches_execcommand_insert_text_in_one_call() -> None:
    locator = _FakeLocator()
    asyncio.run(paste_text(locator, "line one\nline two"))

    assert locator.calls == [("evaluate", "line one\nline two")]
    assert "execCommand" in locator.last_script
    assert "insertText" in locator.last_script

