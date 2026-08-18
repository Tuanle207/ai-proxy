"""Humanized interaction helpers: randomized delays, typing, and mouse movement."""

from __future__ import annotations

import asyncio
import random

from playwright.async_api import Locator, Page


async def human_delay(min_seconds: float = 0.2, max_seconds: float = 0.8) -> None:
    """Sleep a random duration to avoid robotic, evenly-spaced actions."""
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


async def human_type(
    locator: Locator, text: str, *, min_delay_ms: float = 30, max_delay_ms: float = 120
) -> None:
    """Type text into `locator` one character at a time with randomized delays.

    `\\n` is sent as `Shift+Enter` (a literal newline in most chat composers) rather than a bare
    Enter keystroke, which many composers (e.g. Perplexity's) treat as "submit" — typing a bare
    `\n` there would fragment a multi-line prompt into several separately-submitted messages.
    """
    for char in text:
        delay = random.uniform(min_delay_ms, max_delay_ms)
        if char == "\n":
            await locator.press("Shift+Enter", delay=delay)
        else:
            await locator.press_sequentially(char, delay=delay)


async def paste_text(locator: Locator, text: str) -> None:
    """Insert `text` in one shot via `execCommand('insertText')` instead of per-char typing.

    Fast, but only proven to update the host editor's internal (React/Lexical/Slate) state
    correctly on a *freshly loaded* composer — verified live to leave the submit control stuck
    disabled when reused on a composer that already holds a prior conversation/session (see
    `/memories/repo/vcre-ai-proxy.md`). Callers must only use this for fresh threads/projects and
    fall back to `human_type` for resumed ones.
    """
    await locator.evaluate(
        "(el, text) => { el.focus(); document.execCommand('insertText', false, text); }", text
    )


async def human_mouse_jitter(
    page: Page, *, steps: int = 3, width: int = 800, height: int = 600
) -> None:
    """Move the mouse through a few random points to mimic a human presence."""
    for _ in range(steps):
        x = random.uniform(0, width)
        y = random.uniform(0, height)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
