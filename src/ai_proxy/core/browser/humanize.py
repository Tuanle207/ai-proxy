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
    """Type text into `locator` one character at a time with randomized delays."""
    for char in text:
        await locator.press_sequentially(char, delay=random.uniform(min_delay_ms, max_delay_ms))


async def human_mouse_jitter(
    page: Page, *, steps: int = 3, width: int = 800, height: int = 600
) -> None:
    """Move the mouse through a few random points to mimic a human presence."""
    for _ in range(steps):
        x = random.uniform(0, width)
        y = random.uniform(0, height)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
